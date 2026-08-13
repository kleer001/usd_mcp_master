import json

import pytest

from usd_mcp.explain import explain_value, why_not_visible


def test_opinions_are_ranked_strongest_first(shot):
    result = explain_value(shot, "/World/Ball", "radius")
    layers = [opinion["layer"] for opinion in result["authored_opinions"]]

    assert len(layers) == 2
    assert layers[0].endswith("shot.usda")
    assert layers[1].endswith("base.usda")
    assert result["authored_opinions"][0]["wins"] is True
    assert result["authored_opinions"][1]["wins"] is False


def test_losing_opinion_reports_its_own_value(shot):
    result = explain_value(shot, "/World/Ball", "radius")

    assert result["resolved_value"] == 5
    assert result["authored_opinions"][0]["value"] == 5
    assert result["authored_opinions"][1]["value"] == 1


def test_unknown_attribute_raises(shot):
    with pytest.raises(ValueError, match="no attribute"):
        explain_value(shot, "/World/Ball", "nosuchattr")


def test_unknown_prim_raises(shot):
    with pytest.raises(ValueError, match="no prim at"):
        explain_value(shot, "/World/Nope", "radius")


def test_visible_prim_gives_no_reasons(shot):
    result = why_not_visible(shot, "/World/Ball")

    assert result["visible"] is True
    assert result["reasons"] == []


def test_invisible_ancestor_is_named(shot):
    result = why_not_visible(shot, "/World/Hidden/Inner")

    assert result["visible"] is False
    assert len(result["reasons"]) == 1
    assert "/World/Hidden" in result["reasons"][0]
    assert "base.usda" in result["reasons"][0]


def test_deactivated_ancestor_removes_the_prim(shot):
    result = why_not_visible(shot, "/World/Off/Gone")

    assert result["visible"] is False
    assert result["checks"]["exists"] is False
    assert result["checks"]["deepest_existing"] == "/World/Off"


def test_deactivated_prim_itself_is_reported(shot):
    result = why_not_visible(shot, "/World/Off")

    assert result["visible"] is False
    assert "deactivated" in result["reasons"][0]


def test_guide_purpose_is_reported(shot):
    result = why_not_visible(shot, "/World/Guide")

    assert result["visible"] is False
    assert "purpose=guide" in result["reasons"][0]


def test_a_path_that_is_not_a_stage_raises(tmp_path):
    """Fail loudly: a wrong answer about composition is worse than an error."""
    not_a_stage = tmp_path / "notes.txt"
    not_a_stage.write_text("this is not scene description")

    with pytest.raises(ValueError, match="could not open as a USD stage"):
        explain_value(str(not_a_stage), "/World/Ball", "radius")


def test_a_non_imageable_prim_reports_its_actual_type(shot):
    result = why_not_visible(shot, "/World/Surface")

    assert result["visible"] is False
    assert result["checks"]["imageable"] is False
    assert "Material" in result["reasons"][0]
    assert "not an Imageable" in result["reasons"][0]


def test_an_unloaded_payload_is_reported_as_absent(composed):
    """The answer has to match the session being asked about.

    With payloads loaded this prim renders, so a diagnosis that always loads them
    would call it visible while the artist is looking at nothing.
    """
    loaded = why_not_visible(composed, "/Set/Deferred")
    assert loaded["visible"] is True

    deferred = why_not_visible(composed, "/Set/Deferred", load_payloads=False)
    assert deferred["visible"] is False
    assert deferred["checks"]["loaded"] is False
    assert any("unloaded payload" in reason for reason in deferred["reasons"])


def test_array_and_matrix_values_serialise_as_plain_python(shot):
    """USD hands back C++ types; every value in a result has to survive JSON.

    Real stages are mostly vectors and matrices, so a converter that only handled
    scalars would work on this suite and fail on the first asset.
    """
    color = explain_value(shot, "/World/Ball", "primvars:displayColor")
    assert color["resolved_value"] == [[1.0, 0.0, 0.0]]

    transform = explain_value(shot, "/World/Ball", "xformOp:transform")
    assert transform["resolved_value"][0] == [1.0, 0.0, 0.0, 0.0]

    order = explain_value(shot, "/World/Ball", "xformOpOrder")
    assert order["resolved_value"] == ["xformOp:transform"]

    json.dumps(color)
    json.dumps(transform)


def test_an_asset_path_reports_both_what_was_authored_and_what_it_resolves_to(shot, tmp_path):
    """`str()` of an asset path is USD source syntax and drops the resolved location.

    For a texture or a reference that location is the fact worth having, and a null
    one states a broken asset path plainly instead of hiding it in @-wrapped text.
    """
    (tmp_path / "tex").mkdir()
    (tmp_path / "tex" / "diffuse.exr").write_bytes(b"")

    found = explain_value(shot, "/World/Ball", "texture")["resolved_value"]
    assert found == {
        "asset_path": "./tex/diffuse.exr",
        "resolved_path": str(tmp_path / "tex" / "diffuse.exr"),
    }

    missing = explain_value(shot, "/World/Ball", "missingTexture")["resolved_value"]
    assert missing["asset_path"] == "./tex/nosuchfile.exr"
    assert missing["resolved_path"] is None

    json.dumps(found)
