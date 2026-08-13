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
