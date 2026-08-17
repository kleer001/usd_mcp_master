"""The stage profiler, called directly.

The counts are arithmetic; the findings are the reason the tool exists. Each test below
fixes on one trap the numbers imply rather than on the numbers themselves.
"""

import pytest

from usd_mcp.profile import profile_stage

RANGED_USDA = """#usda 1.0
(
    startTimeCode = 1
    endTimeCode = 24
)

def Sphere "Ball"
{
    double radius.timeSamples = {
        1: 1,
        2: 2,
    }
}
"""

STATIC_USDA = """#usda 1.0

def Sphere "Ball"
{
    double radius = 1
}
"""

VARIANT_USDA = """#usda 1.0

def Xform "Prop" (
    variantSets = "lod"
    variants = {
        string lod = "high"
    }
)
{
    variantSet "lod" = {
        "high" {
            def Sphere "Geom"
            {
                double radius = 10
            }
        }
        "low" {
            def Sphere "Geom"
            {
                double radius = 2
            }
        }
    }
}
"""


def test_layers_are_reported_heaviest_first(profiled):
    result = profile_stage(profiled)

    assert [entry["layer"].rsplit("/", 1)[-1] for entry in result["layers"]] == [
        "shot.usda",
        "asset.usda",
    ]
    assert result["layers"][0]["prim_specs"] == 3
    assert result["layers"][1]["attribute_specs"] == 2


def test_the_session_layer_is_not_reported(profiled):
    """A stage always carries one, nobody authored it, and nobody can open it."""
    identifiers = [entry["layer"] for entry in profile_stage(profiled)["layers"]]
    assert identifiers and not any(name.startswith("anon:") for name in identifiers)


def test_animation_that_never_changes_is_named(profiled):
    """The trap: a texture path authored once per frame at the same value."""
    result = profile_stage(profiled)

    assert result["time"]["time_sampled_specs"] == 2
    assert result["time"]["constant_time_sampled_specs"] == 1
    assert "never changes" in result["findings"][0]
    assert result["findings"][0].endswith("asset.usda holds 1 of them.")


def test_a_stage_with_no_animation_reports_no_time_findings(tmp_path):
    static = tmp_path / "static.usda"
    static.write_text(STATIC_USDA)
    result = profile_stage(str(static))

    assert result["time"]["time_sampled_specs"] == 0
    assert result["findings"] == []


def test_animation_without_a_frame_range_is_named(profiled):
    result = profile_stage(profiled)
    assert result["time"]["has_authored_range"] is False
    assert any("no startTimeCode or endTimeCode" in note for note in result["findings"])


def test_an_authored_frame_range_silences_that_finding(tmp_path):
    ranged = tmp_path / "ranged.usda"
    ranged.write_text(RANGED_USDA)
    result = profile_stage(str(ranged))

    assert result["time"]["has_authored_range"] is True
    assert (result["time"]["start_time_code"], result["time"]["end_time_code"]) == (1.0, 24.0)
    assert result["findings"] == []


def test_instance_proxies_are_counted(profiled):
    """`Stage.Traverse()` skips them, and on an instanced set they are most of the scene."""
    result = profile_stage(profiled)

    assert result["prims"]["total"] == 5
    assert result["instancing"] == {
        "prototypes": 1,
        "instances": 1,
        "instanceable_prims": 1,
        "instance_proxies": 1,
        "proxy_share": 0.2,
    }


def test_an_unloaded_payload_is_counted_and_flagged(profiled):
    """The prim carrying the payload composed; only its contents are absent."""
    loaded = profile_stage(profiled, load_payloads=True)
    deferred = profile_stage(profiled, load_payloads=False)

    assert loaded["prims"]["with_payload"] == 1
    assert loaded["prims"]["unloaded_payloads"] == 0
    assert deferred["prims"]["unloaded_payloads"] == 1
    assert deferred["prims"]["total"] == loaded["prims"]["total"] - 1
    assert any("Payloads not loaded: 1 of 1" in note for note in deferred["findings"])


def test_variant_contents_count_as_authored_scene_description(tmp_path):
    """A variant's prims hang off the variant set, not off the prim, and still cost."""
    asset = tmp_path / "variants.usda"
    asset.write_text(VARIANT_USDA)
    layer = profile_stage(str(asset))["layers"][0]

    # /Prop, both /Prop{lod=...} variant prims, and a Geom inside each.
    assert layer["prim_specs"] == 5
    assert layer["attribute_specs"] == 2


def test_a_missing_stage_raises(tmp_path):
    with pytest.raises(ValueError, match="could not open as a USD stage"):
        profile_stage(str(tmp_path / "nosuchfile.usda"))
