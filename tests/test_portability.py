"""The shading portability check, called directly.

Each material in the `looks` fixture is one way a handoff goes, and the interesting
property is that the same material gets a different verdict per target — which is the
whole reason the check takes a target at all.
"""

import pytest
from pxr import Sdr

from usd_mcp.portability import PREVIEW_SURFACE_NODES, TARGETS, check_portability


def verdicts(stage_path, target):
    result = check_portability(stage_path, target)
    return {entry["material"]: entry["verdict"] for entry in result["materials"]}


def test_the_portable_node_set_matches_what_usd_ships():
    """The constant is the contract; the registry is what USD actually registers.

    A node added to the UsdPreviewSurface specification would otherwise read as
    renderer-specific here, silently, and this is where that gets caught.
    """
    registry = Sdr.Registry()
    registered = {
        identifier
        for identifier in registry.GetShaderNodeIdentifiers()
        if str(identifier).startswith("Usd")
    }
    assert registered == PREVIEW_SURFACE_NODES


def test_every_target_resolves_to_a_context():
    assert set(TARGETS.values()) == {"", "glslfx", "ri", "arnold", "mtlx"}


def test_a_renderman_target_reads_what_was_authored_for_it(looks):
    assert verdicts(looks, "renderman") == {
        "/Looks/Portable": "preview_fallback",
        "/Looks/Both": "native",
        "/Looks/RiOnly": "native",
        "/Looks/Mislabelled": "renderer_specific",
        "/Looks/Empty": "unreadable",
    }


def test_another_renderer_loses_the_renderman_only_material(looks):
    """The same stage, a different destination, and a material that stops rendering."""
    assert verdicts(looks, "arnold") == {
        "/Looks/Portable": "preview_fallback",
        "/Looks/Both": "preview_fallback",
        "/Looks/RiOnly": "unreadable",
        "/Looks/Mislabelled": "renderer_specific",
        "/Looks/Empty": "unreadable",
    }


def test_the_universal_target_accepts_only_the_portable_set(looks):
    """A universal output wired to a renderer's own shader claims what it cannot keep."""
    assert verdicts(looks, "preview") == {
        "/Looks/Portable": "native",
        "/Looks/Both": "native",
        "/Looks/RiOnly": "unreadable",
        "/Looks/Mislabelled": "renderer_specific",
        "/Looks/Empty": "unreadable",
    }


def test_a_native_network_is_not_judged_against_the_portable_set(looks):
    """`Both` wires PxrSurface to its own ri output, which is the point of doing so."""
    both = next(
        m for m in check_portability(looks, "ri")["materials"] if m["material"] == "/Looks/Both"
    )
    surface = both["terminals"]["surface"]

    assert both["verdict"] == "native"
    assert surface["resolved_from_universal"] is False
    assert surface["unportable_shaders"] == ["PxrSurface"]


def test_the_whole_network_is_walked_not_just_the_terminal(looks):
    """A texture two connections down still has to be readable at the far end."""
    portable = next(
        m
        for m in check_portability(looks, "preview")["materials"]
        if m["material"] == "/Looks/Portable"
    )
    shaders = portable["terminals"]["surface"]["shaders"]

    # The texture feeds two inputs and is reported once.
    assert [entry["id"] for entry in shaders] == ["UsdPreviewSurface", "UsdUVTexture"]
    assert all(entry["registered_here"] for entry in shaders)


def test_an_unconnected_output_is_not_a_provision(looks):
    """USD creates an output on request; a caller that stopped there authored nothing."""
    portable = next(
        m
        for m in check_portability(looks, "preview")["materials"]
        if m["material"] == "/Looks/Portable"
    )
    assert portable["contexts"] == [""]
    assert list(portable["terminals"]) == ["surface"]


def test_an_unregistered_shader_id_is_reported_as_such(looks):
    result = check_portability(looks, "ri")
    rionly = next(m for m in result["materials"] if m["material"] == "/Looks/RiOnly")

    assert rionly["terminals"]["surface"]["shaders"][0]["registered_here"] is False
    assert any("PxrSurface" in note for note in result["findings"])


def test_authored_contexts_are_reported_per_material(looks):
    contexts = {
        entry["material"]: entry["contexts"]
        for entry in check_portability(looks, "preview")["materials"]
    }
    assert contexts["/Looks/Both"] == ["", "ri"]
    assert contexts["/Looks/RiOnly"] == ["ri"]
    assert contexts["/Looks/Empty"] == []


def test_readable_is_false_while_anything_is_unaccounted_for(looks):
    result = check_portability(looks, "ri")
    assert result["readable"] is False
    assert result["summary"]["materials"] == 5


def test_an_unknown_target_is_refused(looks):
    """A context nobody verified would produce a confident answer about a host."""
    with pytest.raises(ValueError, match="unknown target 'karma'"):
        check_portability(looks, "karma")


def test_a_missing_stage_raises(tmp_path):
    with pytest.raises(ValueError, match="could not open as a USD stage"):
        check_portability(str(tmp_path / "nosuchfile.usda"), "preview")
