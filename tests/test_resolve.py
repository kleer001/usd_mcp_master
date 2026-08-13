import pytest

from usd_mcp.resolve import resolve_path


def test_a_relative_path_resolves_against_its_anchor(composed, tmp_path):
    result = resolve_path(composed, "./prop.usda")

    assert result["resolved"] is True
    assert result["exists"] is True
    assert result["resolved_path"] == str(tmp_path / "prop.usda")
    assert result["anchor_layer"].endswith("shot.usda")


def test_a_missing_file_reports_where_it_looked(composed):
    result = resolve_path(composed, "./nosuchfile.usda")

    assert result["resolved"] is False
    assert result["resolved_path"] is None
    assert result["exists"] is False
    assert "does not resolve" in result["explanation"]
    assert result["anchor_layer"] in result["explanation"]


def test_the_resolver_and_context_are_reported(composed):
    result = resolve_path(composed, "./prop.usda")

    assert result["resolver"] == "DefaultResolver"
    assert "ResolverContext" in result["resolver_context"]


def test_an_absolute_path_resolves_without_an_anchor(composed):
    result = resolve_path(composed, composed)

    assert result["resolved_path"] == composed


def test_anchoring_to_a_referenced_layer_is_allowed(composed, tmp_path):
    """A path authored inside an asset anchors to that asset, not to the root."""
    result = resolve_path(composed, "./payload.usda", anchor_layer=str(tmp_path / "set.usda"))

    assert result["anchor_layer"].endswith("set.usda")
    assert result["resolved"] is True


def test_a_layer_the_stage_does_not_use_is_refused(composed):
    with pytest.raises(ValueError, match="is not a layer used by"):
        resolve_path(composed, "./prop.usda", anchor_layer="/nowhere/other.usda")
