"""The stage diff, called directly.

The tolerance is the reason this tool exists, so most of these fix on the one case a
text diff cannot tell apart: a layer re-exported with float noise against a layer
somebody actually edited.
"""

import pytest

from usd_mcp.diff import diff_stages

PROTOTYPE_USDA = """#usda 1.0

def Xform "Prop"
{
    def Sphere "Geom"
    {
        double radius = %s
    }
}
"""

ANIM_USDA = """#usda 1.0

def Sphere "Ball"
{
    double radius.timeSamples = {
%s    }
}
"""

FLAG_USDA = """#usda 1.0

def Sphere "Ball"
{
    bool doubleSided = %s
}
"""

SPARSE_USDA = """#usda 1.0

def Sphere "Ball"
{
    double radius = 1
%s}
"""

INSTANCED_SET_USDA = """#usda 1.0

def Xform "Set"
{
    def "Prop" (
        instanceable = true
        references = @./%s@</Prop>
    )
    {
    }
}
"""


def test_exact_diff_reports_every_difference(drifted):
    a, b = drifted
    result = diff_stages(a, b)

    assert result["identical"] is False
    assert [p["path"] for p in result["prims_added"]] == ["/World/Added"]
    assert [p["path"] for p in result["prims_removed"]] == ["/World/Gone"]
    assert result["prims_retyped"] == [
        {"path": "/World/Retyped", "type_name_a": "Sphere", "type_name_b": "Cube"}
    ]
    assert {c["attribute"] for c in result["attributes_changed"]} == {
        "radius",
        "primvars:displayColor",
        "spin",
    }
    assert result["counts"]["within_tolerance"] == 0


def test_tolerance_absorbs_float_noise_and_counts_it(drifted):
    """The whole point: noise stops being reported, and is reported as noise instead."""
    a, b = drifted
    result = diff_stages(a, b, tolerance=1e-3)

    assert [c["attribute"] for c in result["attributes_changed"]] == ["primvars:displayColor"]
    assert result["counts"]["within_tolerance"] == 2
    assert result["identical"] is False


def test_tolerance_does_not_absorb_a_real_edit(drifted):
    """A colour that changed from red to green is not float noise at any tolerance."""
    a, b = drifted
    changed = diff_stages(a, b, tolerance=0.1)["attributes_changed"]
    colour = next(c for c in changed if c["attribute"] == "primvars:displayColor")
    assert colour["value_a"] == [[1.0, 0.0, 0.0]]
    assert colour["value_b"] == [[0.0, 1.0, 0.0]]


def test_a_stage_does_not_differ_from_itself(drifted):
    a, _ = drifted
    result = diff_stages(a, a)
    assert result["identical"] is True
    assert result["counts"]["attributes_changed"] == 0


def test_animation_difference_is_found_and_summarised(drifted):
    """A default-time comparison alone would call two different curves identical.

    `spin` has time samples and no default, so `Get()` at default time returns the same
    thing on both sides. The sample series is what differs.
    """
    a, b = drifted
    spin = next(c for c in diff_stages(a, b)["attributes_changed"] if c["attribute"] == "spin")

    assert spin["value_a"] is None and spin["value_b"] is None
    assert spin["time_samples"] == {
        "count_a": 2,
        "count_b": 2,
        "first_differing_time": 2.0,
    }


def test_an_attribute_authored_on_one_side_only_is_flagged(tmp_path):
    """Absence is a difference, and is reported as absence rather than as a value."""
    a = tmp_path / "sparse_a.usda"
    b = tmp_path / "sparse_b.usda"
    a.write_text(SPARSE_USDA % "")
    b.write_text(SPARSE_USDA % '    token visibility = "invisible"\n')

    assert diff_stages(str(a), str(b))["attributes_changed"] == [
        {
            "prim": "/Ball",
            "attribute": "visibility",
            "authored_a": False,
            "authored_b": True,
            "value_a": None,
            "value_b": "invisible",
            "time_samples": None,
        }
    ]


def test_a_change_inside_an_instanced_asset_is_found(tmp_path):
    """`Stage.Traverse()` skips instance proxies; a diff that used it would see nothing."""
    paths = []
    for name, radius in (("a", "1"), ("b", "9")):
        (tmp_path / f"prop_{name}.usda").write_text(PROTOTYPE_USDA % radius)
        set_path = tmp_path / f"set_{name}.usda"
        set_path.write_text(INSTANCED_SET_USDA % f"prop_{name}.usda")
        paths.append(str(set_path))

    result = diff_stages(*paths)
    assert [(c["prim"], c["value_a"], c["value_b"]) for c in result["attributes_changed"]] == [
        ("/Set/Prop/Geom", 1.0, 9.0)
    ]


def test_layer_scope_ignores_composition(shot, tmp_path):
    """A composed diff resolves the sublayer; a per-layer diff reads one file only."""
    base = str(tmp_path / "base.usda")

    composed = diff_stages(shot, base, scope="composed")
    radius = next(c for c in composed["attributes_changed"] if c["attribute"] == "radius")
    assert (radius["value_a"], radius["value_b"]) == (5.0, 1.0)

    per_layer = diff_stages(shot, base, scope="layer")
    # shot.usda authors one override and nothing else; base.usda authors the whole scene.
    assert [p["path"] for p in per_layer["prims_added"]] == [
        "/World/Guide",
        "/World/Hidden",
        "/World/Hidden/Inner",
        "/World/Off",
        "/World/Off/Gone",
        "/World/Surface",
    ]
    assert per_layer["prims_removed"] == []


def test_layer_scope_sees_a_prim_that_composes_away(shot, tmp_path):
    """`/World/Off/Gone` is authored under a deactivated prim, so it never composes."""
    base = str(tmp_path / "base.usda")
    composed = {p["path"] for p in diff_stages(shot, base, scope="composed")["prims_added"]}
    per_layer = {p["path"] for p in diff_stages(shot, base, scope="layer")["prims_added"]}

    assert "/World/Off/Gone" in per_layer
    assert "/World/Off/Gone" not in composed


def _anim_pair(tmp_path, samples_a, samples_b):
    a = tmp_path / "anim_a.usda"
    b = tmp_path / "anim_b.usda"
    a.write_text(ANIM_USDA % samples_a)
    b.write_text(ANIM_USDA % samples_b)
    return diff_stages(str(a), str(b))["attributes_changed"][0]["time_samples"]


def test_a_sample_added_at_the_end_is_found(tmp_path):
    """The series agree everywhere they overlap; the difference is the tail."""
    assert _anim_pair(tmp_path, "1: 0,\n", "1: 0,\n        2: 5,\n") == {
        "count_a": 1,
        "count_b": 2,
        "first_differing_time": 2.0,
    }


def test_a_shifted_sample_time_is_found(tmp_path):
    """Retiming holds the values and moves the times, which is still a difference."""
    assert _anim_pair(tmp_path, "1: 0,\n        2: 5,\n", "1: 0,\n        3: 5,\n") == {
        "count_a": 2,
        "count_b": 2,
        "first_differing_time": 2.0,
    }


def test_tolerance_never_absorbs_a_flipped_boolean(tmp_path):
    """False and True are one apart as numbers, and not comparable as numbers."""
    a = tmp_path / "flag_a.usda"
    b = tmp_path / "flag_b.usda"
    a.write_text(FLAG_USDA % "false")
    b.write_text(FLAG_USDA % "true")

    changed = diff_stages(str(a), str(b), tolerance=2.0)["attributes_changed"]
    assert [(c["value_a"], c["value_b"]) for c in changed] == [(False, True)]


def test_a_negative_tolerance_is_refused(drifted):
    a, b = drifted
    with pytest.raises(ValueError, match="tolerance must not be negative"):
        diff_stages(a, b, tolerance=-1.0)


def test_an_unknown_scope_is_refused(drifted):
    a, b = drifted
    with pytest.raises(ValueError, match="scope must be one of"):
        diff_stages(a, b, scope="authored")


def test_a_missing_stage_raises(drifted, tmp_path):
    a, _ = drifted
    missing = str(tmp_path / "nosuchfile.usda")
    with pytest.raises(ValueError, match="could not open as a USD stage"):
        diff_stages(a, missing)


def test_a_missing_layer_raises(drifted, tmp_path):
    a, _ = drifted
    missing = str(tmp_path / "nosuchfile.usda")
    with pytest.raises(ValueError, match="could not open as a USD layer"):
        diff_stages(a, missing, scope="layer")


def test_a_malformed_layer_raises(drifted, tmp_path):
    a, _ = drifted
    broken = tmp_path / "broken.usda"
    broken.write_text("this is not scene description")
    with pytest.raises(ValueError, match="could not open as a USD layer"):
        diff_stages(a, str(broken), scope="layer")
