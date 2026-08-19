"""The write path, which only exists when the server is built with writes enabled."""

import json

import pytest

from usd_mcp.explain import explain_value, why_not_visible
from usd_mcp.write import set_active, set_attribute, set_visibility


@pytest.fixture(autouse=True)
def audit_log(tmp_path, monkeypatch):
    """Keep the audit log inside the test's tmp_path rather than the developer's home."""
    path = tmp_path / "audit.log"
    monkeypatch.setenv("USD_MCP_AUDIT_LOG", str(path))
    return path


def entries(audit_log):
    if not audit_log.exists():
        return []
    return [json.loads(line) for line in audit_log.read_text().splitlines()]


def test_the_default_call_writes_nothing(shot, audit_log):
    """The dry run is what the tool does by default, not a step a caller may skip."""
    before = explain_value(shot, "/World/Ball", "radius")["resolved_value"]

    result = set_attribute(shot, "/World/Ball", "radius", 9.0, shot)

    assert result["applied"] is False
    assert result["confirmed"] is False
    assert result["change"] == {"kind": "attribute", "name": "radius", "from": 5.0, "to": 9.0}
    assert "Dry run" in result["explanation"]
    assert explain_value(shot, "/World/Ball", "radius")["resolved_value"] == before
    assert entries(audit_log) == []


def test_a_confirmed_edit_lands_in_the_named_layer(shot, audit_log):
    result = set_attribute(shot, "/World/Ball", "radius", 9.0, shot, confirm=True)

    assert result["applied"] is True
    assert result["resolved_value_after"] == 9.0

    after = explain_value(shot, "/World/Ball", "radius")
    assert after["resolved_value"] == 9.0
    assert after["authored_opinions"][0]["layer"].endswith("shot.usda")
    assert len(entries(audit_log)) == 1


def test_an_edit_into_a_weak_layer_is_applied_and_reported_as_not_moving_the_value(
    shot, tmp_path, audit_log
):
    """Authoring a losing opinion is legitimate — fixing an asset a shot overrides.

    So it is applied where asked, and the result says plainly that the resolved value
    did not move rather than implying the edit took effect.
    """
    result = set_attribute(shot, "/World/Ball", "radius", 3.0, str(tmp_path / "base.usda"),
                           confirm=True)

    assert result["applied"] is True
    assert result["blocked_by"] == "strength"
    assert result["resolved_value_after"] == 5.0
    assert "did not change" in result["explanation"]

    opinions = explain_value(shot, "/World/Ball", "radius")["authored_opinions"]
    assert [o["value"] for o in opinions] == [5.0, 3.0]


def test_visibility_reports_that_an_invisible_ancestor_still_wins(shot, audit_log):
    """Visibility inherits, so authoring `inherited` on a child reveals nothing."""
    result = set_visibility(shot, "/World/Hidden/Inner", True, shot, confirm=True)

    assert result["applied"] is True
    assert result["resolved_value_after"] == "invisible"
    assert "ancestor" in result["explanation"]
    assert why_not_visible(shot, "/World/Hidden/Inner")["visible"] is False


def test_hiding_a_prim_takes_effect(shot):
    set_visibility(shot, "/World/Ball", False, shot, confirm=True)

    assert why_not_visible(shot, "/World/Ball")["visible"] is False


def test_deactivating_a_prim_removes_its_subtree(shot):
    result = set_active(shot, "/World/Hidden", False, shot, confirm=True)

    assert result["applied"] is True
    assert result["resolved_value_after"] is False
    assert why_not_visible(shot, "/World/Hidden/Inner")["checks"]["exists"] is False


def test_a_packaged_layer_is_refused(packaged):
    with pytest.raises(ValueError, match="cannot be authored into"):
        set_attribute(packaged, "/World/Ball", "radius", 2.0, packaged, confirm=True)


def test_a_layer_outside_the_root_stack_is_refused(shot, tmp_path):
    with pytest.raises(ValueError, match="not in the root layer stack"):
        set_attribute(shot, "/World/Ball", "radius", 2.0, "/nowhere/other.usda", confirm=True)


def test_an_unknown_attribute_is_refused_rather_than_invented(shot):
    with pytest.raises(ValueError, match="no attribute"):
        set_attribute(shot, "/World/Ball", "nosuchattr", 1.0, shot, confirm=True)


def test_a_value_of_the_wrong_type_is_refused(shot, audit_log):
    with pytest.raises(ValueError, match="could not author"):
        set_attribute(shot, "/World/Ball", "radius", "banana", shot, confirm=True)

    assert entries(audit_log) == []


def test_visibility_on_a_non_imageable_prim_is_refused(shot):
    with pytest.raises(ValueError, match="not an Imageable"):
        set_visibility(shot, "/World/Surface", False, shot, confirm=True)


def test_array_values_survive_the_round_trip(shot):
    set_attribute(shot, "/World/Ball", "primvars:displayColor", [[0, 1, 0]], shot, confirm=True)

    assert explain_value(shot, "/World/Ball", "primvars:displayColor")["resolved_value"] == [
        [0.0, 1.0, 0.0]
    ]


def test_the_audit_log_names_layer_prim_attribute_and_both_values(shot, audit_log):
    set_attribute(shot, "/World/Ball", "radius", 9.0, shot, confirm=True)
    record = entries(audit_log)[0]

    assert record["prim"] == "/World/Ball"
    assert record["name"] == "radius"
    assert record["from"] == 5.0
    assert record["to"] == 9.0
    assert record["layer"].endswith("shot.usda")
    assert record["stage"] == shot
    assert record["time"].startswith("20")


def test_every_applied_mutation_is_logged(shot, audit_log):
    set_attribute(shot, "/World/Ball", "radius", 9.0, shot, confirm=True)
    set_visibility(shot, "/World/Ball", False, shot, confirm=True)
    set_active(shot, "/World/Guide", False, shot, confirm=True)

    assert [record["name"] for record in entries(audit_log)] == [
        "radius",
        "visibility",
        "active",
    ]


def test_visibility_defaults_to_a_dry_run(shot, audit_log):
    result = set_visibility(shot, "/World/Ball", False, shot)

    assert result["applied"] is False
    assert why_not_visible(shot, "/World/Ball")["visible"] is True
    assert entries(audit_log) == []


def test_active_defaults_to_a_dry_run(shot, audit_log):
    result = set_active(shot, "/World/Guide", False, shot)

    assert result["applied"] is False
    assert result["change"] == {"kind": "metadata", "name": "active", "from": True, "to": False}
    assert entries(audit_log) == []


def test_active_reports_being_outranked_by_a_stronger_layer(shot, tmp_path):
    """`active` is metadata with no AttributeQuery, so strength is settled separately."""
    set_active(shot, "/World/Ball", False, shot, confirm=True)

    result = set_active(shot, "/World/Ball", True, str(tmp_path / "base.usda"))

    assert result["would_win"] is False
    assert result["blocked_by"] == "strength"
    assert result["outranked_by"]["layer"].endswith("shot.usda")
    assert result["outranked_by"]["value"] is False


def test_authoring_on_an_instance_proxy_is_refused(composed, audit_log):
    """USD discards an opinion authored at a proxy path, so writing one is a silent no-op."""
    with pytest.raises(ValueError, match="instance proxy"):
        set_attribute(composed, "/Set/PropB/Geom", "radius", 4.0, composed, confirm=True)
    with pytest.raises(ValueError, match="instance proxy"):
        set_visibility(composed, "/Set/PropB/Geom", False, composed, confirm=True)

    assert entries(audit_log) == []


def test_a_large_value_is_bounded_in_the_report_and_whole_in_the_audit_log(tmp_path, monkeypatch):
    """The two halves of a write pull in opposite directions, and both must hold.

    What comes back is bounded, because an agent cannot spend its context window on
    three-quarters of a million points. What the audit log records is not, because a
    record of the leading elements is not a record of what was authored.

    The dry run — the default call — must not pay for the whole conversion either: it
    reports a few hundred elements, so it converts a few hundred.
    """
    from pxr import Gf, Usd, UsdGeom, Vt

    from usd_mcp.write import set_attribute

    log = tmp_path / "audit.log"
    monkeypatch.setenv("USD_MCP_AUDIT_LOG", str(log))

    stage_path = tmp_path / "mesh.usda"
    stage = Usd.Stage.CreateNew(str(stage_path))
    mesh = UsdGeom.Mesh.Define(stage, "/Mesh")
    points = Vt.Vec3fArray([Gf.Vec3f(index, 0.0, 1.5) for index in range(5000)])
    mesh.GetPointsAttr().Set(points)
    stage.GetRootLayer().Save()

    plan = set_attribute(str(stage_path), "/Mesh", "points", points, str(stage_path))
    reported = plan["change"]["from"]

    assert plan["applied"] is False
    assert reported["elements_truncated"] == {
        "reported": len(reported["elements"]),
        "total": 5000,
    }
    assert len(reported["elements"]) < 5000

    applied = set_attribute(
        str(stage_path), "/Mesh", "points", points, str(stage_path), confirm=True
    )
    assert applied["applied"] is True
    assert applied["resolved_value_after"]["elements_truncated"]["total"] == 5000

    entry = json.loads(log.read_text().strip().splitlines()[-1])
    assert len(entry["from"]) == 5000
    assert len(entry["to"]) == 5000
    assert entry["to"][-1] == [4999.0, 0.0, 1.5]
