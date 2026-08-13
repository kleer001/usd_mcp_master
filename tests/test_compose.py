import pytest

from usd_mcp.compose import explain_edit_target, explain_prim, explain_variants


def test_arcs_are_reported_strongest_first(composed):
    result = explain_prim(composed, "/Set/PropA")
    arcs = result["composition_arcs"]

    assert [arc["arc_type"] for arc in arcs] == ["root", "reference", "variant"]
    assert arcs[0]["target_layer"].endswith("shot.usda")
    assert arcs[1]["target_layer"].endswith("prop.usda")
    assert arcs[1]["target_prim_path"] == "/Prop"


def test_payload_arc_is_distinguished_from_a_reference(composed):
    result = explain_prim(composed, "/Set/Deferred")

    assert [arc["arc_type"] for arc in result["composition_arcs"]] == ["root", "payload"]


def test_instance_proxy_is_flagged_as_uneditable(composed):
    result = explain_prim(composed, "/Set/PropB/Geom")

    assert result["instancing"]["is_instance_proxy"] is True
    assert "ignored" in result["instancing"]["note"]


def test_instance_root_names_its_prototype(composed):
    result = explain_prim(composed, "/Set/PropB")

    assert result["instancing"]["is_instance"] is True
    assert result["instancing"]["prototype"].startswith("/__Prototype")


def test_uninstanced_prim_carries_no_instancing_note(composed):
    result = explain_prim(composed, "/Set/PropA")

    assert result["instancing"]["is_instance"] is False
    assert result["instancing"]["note"] is None


def test_layer_stack_omits_the_session_layer(composed):
    result = explain_prim(composed, "/Set/PropA")

    assert not any("session" in layer for layer in result["layer_stack"])


def test_unknown_prim_raises(composed):
    with pytest.raises(ValueError, match="no prim at"):
        explain_prim(composed, "/Set/Nope")


def test_shot_selection_beats_the_assets_own(composed):
    result = explain_variants(composed, "/Set/PropA")
    lod = result["variant_sets"][0]

    assert lod["name"] == "lod"
    assert lod["selection"] == "low"
    assert sorted(lod["variants"]) == ["high", "low"]

    assert lod["selected_in"][0]["layer"].endswith("shot.usda")
    assert lod["selected_in"][0]["selection"] == "low"
    assert lod["selected_in"][0]["wins"] is True
    assert lod["selected_in"][1]["layer"].endswith("prop.usda")
    assert lod["selected_in"][1]["selection"] == "high"
    assert lod["selected_in"][1]["wins"] is False


def test_prim_without_variant_sets_reports_none(composed):
    assert explain_variants(composed, "/Set/Deferred")["variant_sets"] == []


def test_edit_into_a_weak_layer_is_reported_as_losing(shot, tmp_path):
    result = explain_edit_target(shot, "/World/Ball", "radius", str(tmp_path / "base.usda"))

    assert result["would_win"] is False
    assert result["outranked_by"]["layer"].endswith("shot.usda")
    assert result["outranked_by"]["value"] == 5
    assert result["value_that_would_survive"] == 5
    assert "would lose" in result["explanation"]


def test_edit_into_the_strongest_layer_is_reported_as_winning(shot):
    result = explain_edit_target(shot, "/World/Ball", "radius", shot)

    assert result["would_win"] is True
    assert result["outranked_by"] is None
    assert result["value_that_would_survive"] is None
    assert "would win" in result["explanation"]


def test_winning_is_decided_by_authored_opinions_not_the_schema_fallback(composed):
    """A Sphere's `radius` falls back to 1.0, which is not an authored opinion.

    Resolving with nothing stronger authored still returns that fallback, so a check
    written against the resolved value would call every edit outranked.
    """
    result = explain_edit_target(composed, "/Set/PropA/Geom", "radius", composed)

    assert result["would_win"] is True
    assert result["outranked_by"] is None


def test_a_layer_outside_the_root_stack_is_refused(shot, tmp_path):
    with pytest.raises(ValueError, match="not in the root layer stack"):
        explain_edit_target(shot, "/World/Ball", "radius", str(tmp_path / "prop.usda"))


def test_unknown_attribute_raises(shot):
    with pytest.raises(ValueError, match="no attribute"):
        explain_edit_target(shot, "/World/Ball", "nosuchattr", shot)


def test_a_packaged_layer_cannot_be_authored_into(packaged):
    """Strength is the wrong question when the file can never be written.

    USD accepts the edit in memory and raises `writing package usdz layer is not
    allowed` on save, so reporting this as a winning edit sends a caller to author
    into a layer that cannot keep it.
    """
    result = explain_edit_target(packaged, "/World/Ball", "radius", packaged)

    assert result["target_writable"] is False
    assert result["would_win"] is False
    assert result["blocked_by"] == "read_only_layer"
    assert result["outranked_by"] is None
    assert "cannot be authored into" in result["explanation"]


def test_a_writable_layer_is_not_blocked(shot):
    result = explain_edit_target(shot, "/World/Ball", "radius", shot)

    assert result["target_writable"] is True
    assert result["blocked_by"] is None


def test_being_outranked_is_reported_as_a_strength_problem(shot, tmp_path):
    result = explain_edit_target(shot, "/World/Ball", "radius", str(tmp_path / "base.usda"))

    assert result["blocked_by"] == "strength"
    assert result["target_writable"] is True


def test_an_instance_proxy_cannot_hold_an_opinion_in_any_layer(composed):
    """A proxy has no prim index of its own, so a resolve target against it raises
    from inside USD. It also cannot hold an opinion, which is the answer worth giving.
    """
    result = explain_edit_target(composed, "/Set/PropB/Geom", "radius", composed)

    assert result["would_win"] is False
    assert result["blocked_by"] == "instance_proxy"
    assert result["outranked_by"] is None
    assert "discarded" in result["explanation"]
