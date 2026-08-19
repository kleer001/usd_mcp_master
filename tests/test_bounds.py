"""The bound on result payload size, and the honesty it is required to keep.

A result an agent cannot fit in its context window is not a smaller answer, it is no
answer. Measured on a 200-layer, 10,000-prim stage before the bound existed,
`diff_stages` returned 1.59 MB and `profile_stage` 78 KB — enough on its own to end the
conversation the question was asked in.

So every list a stage can make arbitrarily long is trimmed. The trim is the easy half.
The half worth testing is that a trimmed list always says it was trimmed, and that the
aggregate counts beside it still count everything: a bound that quietly reports a slice of
ten thousand is a confident wrong answer, which is exactly what this package refuses to
give anywhere else.
"""

import json

import pytest

from usd_mcp import common
from usd_mcp.common import bounded, bounded_value, value_brief
from usd_mcp.compose import explain_prim, explain_variants
from usd_mcp.diff import diff_stages
from usd_mcp.explain import explain_value
from usd_mcp.portability import check_portability
from usd_mcp.profile import profile_stage
from usd_mcp.write import set_attribute

# Small enough that a modest fixture reaches it. The shipped budget is set above
# anything real assets produce, so a fixture large enough to trip it would be a fixture
# testing its own size rather than the code.
LOWERED_BUDGET = 200


@pytest.fixture
def tight_values(monkeypatch):
    """Shrink the value budget so a modest array exercises the trim."""
    monkeypatch.setattr(common, "MAX_VALUE_BYTES", 100)
    return 100


@pytest.fixture
def lowered_limit(monkeypatch):
    """Shrink the field budget so a small fixture exercises the trim.

    `bounded()` reads `MAX_FIELD_BYTES` per call rather than freezing it as a default
    argument, which is what makes this possible.
    """
    monkeypatch.setattr(common, "MAX_FIELD_BYTES", LOWERED_BUDGET)
    return LOWERED_BUDGET


def assert_bounded(result, field, total):
    """The field was trimmed and says so, naming what it left out.

    The reported count is whatever fit in the budget rather than a fixed number, so the
    assertion is on the relationship: something was kept, not everything, and the marker
    agrees with the list beside it.
    """
    reported = result[f"{field}_truncated"]["reported"]
    assert 0 < reported < total
    assert len(result[field]) == reported
    assert result[f"{field}_truncated"]["total"] == total


class TestBounded:
    def test_a_short_list_passes_through_whole(self):
        assert bounded("things", [1, 2, 3]) == {"things": [1, 2, 3]}

    def test_a_list_that_fits_the_budget_is_not_truncated(self):
        items = list(range(50))
        assert bounded("things", items) == {"things": items}

    def test_entries_are_priced_so_fat_ones_are_trimmed_sooner(self):
        """The point of a byte budget: cost decides the count, not the count the cost."""
        thin = bounded("things", ["a"] * 500, budget=200)
        fat = bounded("things", ["a" * 40] * 500, budget=200)
        assert thin["things_truncated"]["reported"] > fat["things_truncated"]["reported"]

    def test_one_entry_is_always_reported_however_large(self):
        """A field answering with nothing says less than one answering with too much."""
        result = bounded("things", ["x" * 5000, "y" * 5000], budget=10)
        assert len(result["things"]) == 1
        assert result["things_truncated"] == {"reported": 1, "total": 2}

    def test_the_truncation_key_is_absent_rather_than_empty(self):
        """Its presence is the signal, so a caller can test for it and nothing else."""
        assert "things_truncated" not in bounded("things", [1, 2, 3])

    def test_a_long_list_keeps_the_front_and_reports_the_whole(self):
        result = bounded("things", list(range(500)), budget=100)
        reported = result["things_truncated"]["reported"]
        assert result["things"] == list(range(reported))
        assert result["things_truncated"]["total"] == 500


class TestDiffBounds:
    def test_every_itemised_list_is_bounded(self, wide, lowered_limit):
        result = diff_stages(*wide)
        for field in (
            "prims_added",
            "prims_removed",
            "prims_retyped",
            "attributes_changed",
        ):
            assert_bounded(result, field, 60)

    def test_counts_are_of_everything_not_of_what_was_reported(self, wide, lowered_limit):
        """The bound trims the itemisation; it must not trim the arithmetic."""
        result = diff_stages(*wide)
        assert result["counts"]["added"] == 60
        assert result["counts"]["removed"] == 60
        assert result["counts"]["retyped"] == 60
        assert result["counts"]["attributes_changed"] == 60

    def test_a_small_diff_is_reported_whole(self, drifted):
        result = diff_stages(*drifted, tolerance=1e-6)
        assert not any(key.endswith("_truncated") for key in result)

    def test_identical_survives_the_bound(self, wide, lowered_limit):
        """`identical` is computed before the trim, so a bounded diff is still not one."""
        assert diff_stages(wide[0], wide[0])["identical"] is True
        assert diff_stages(*wide)["identical"] is False


class TestProfileBounds:
    def test_the_layer_list_and_layer_stack_are_bounded(self, wide, lowered_limit):
        result = profile_stage(wide[0])
        assert_bounded(result, "layers", 61)
        assert_bounded(result, "root_layer_stack", 61)

    def test_the_costliest_layers_are_the_ones_kept(self, wide, lowered_limit):
        """Sorted before trimming, so the bound drops the cheap end, not an arbitrary one."""
        result = profile_stage(wide[0])
        specs = [entry["prim_specs"] for entry in result["layers"]]
        assert specs == sorted(specs, reverse=True)

    def test_time_totals_are_summed_over_every_layer(self, profiled):
        result = profile_stage(profiled)
        assert result["time"]["time_sampled_specs"] == sum(
            entry["time_sampled_specs"] for entry in result["layers"]
        )


class TestExplainBounds:
    def test_the_opinion_stack_and_layer_stack_are_bounded(self, wide, lowered_limit):
        result = explain_value(wide[0], "/World/Contested", "size")
        assert_bounded(result, "authored_opinions", 60)
        assert_bounded(result, "layer_stack", 61)

    def test_the_winning_opinion_survives_the_bound(self, wide, lowered_limit):
        """Strongest first, so the opinion that decided the value is never the one cut."""
        result = explain_value(wide[0], "/World/Contested", "size")
        assert result["authored_opinions"][0]["wins"] is True
        assert result["authored_opinions"][0]["strength"] == 0

    def test_explain_prim_bounds_its_layer_stack(self, wide, lowered_limit):
        assert_bounded(explain_prim(wide[0], "/World/Contested"), "layer_stack", 61)


class TestPortabilityBounds:
    def test_the_material_list_is_bounded(self, wide, lowered_limit):
        assert_bounded(check_portability(wide[0], "preview"), "materials", 60)

    def test_the_summary_counts_every_material(self, wide, lowered_limit):
        result = check_portability(wide[0], "preview")
        assert result["summary"]["materials"] == 60
        assert result["summary"]["unreadable"] == 60

    def test_the_worst_materials_are_the_ones_kept(self, looks):
        """Sorted worst first, so a bound drops what would have rendered anyway.

        The expected order is written out rather than derived from `_SEVERITY`. Sorting
        the expectation with the same table the code sorts by proves the sort call runs,
        not that it runs the right way round — swap two entries in `_SEVERITY` and a
        test written that way still passes. This order is the one SPEC.md publishes.
        """
        materials = check_portability(looks, "renderman")["materials"]
        verdicts = [entry["verdict"] for entry in materials]
        worst_first = ["unreadable", "renderer_specific", "preview_fallback", "native"]

        assert verdicts == sorted(verdicts, key=worst_first.index)
        assert set(verdicts) == set(worst_first), "the fixture no longer covers every verdict"

    def test_findings_read_every_material_not_the_bounded_slice(self, wide, lowered_limit):
        """A count of what will not survive is only true if it counted all of them."""
        findings = check_portability(wide[0], "preview")["findings"]
        assert any("60" in finding for finding in findings)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda w: diff_stages(*w), id="diff_stages"),
        pytest.param(lambda w: profile_stage(w[0]), id="profile_stage"),
        pytest.param(
            lambda w: explain_value(w[0], "/World/Contested", "size"), id="explain_value"
        ),
        pytest.param(
            lambda w: check_portability(w[0], "preview"), id="check_portability"
        ),
    ],
)
def test_no_result_is_large_enough_to_cost_a_context_window(call, wide):
    """The bound is worth having only if it lands somewhere an agent can afford.

    Twenty-five kilobytes is roughly six thousand tokens — a readable fraction of a
    context window rather than the whole of one.
    """
    assert len(json.dumps(call(wide))) < 25_000


class TestBoundedValue:
    """A single authored value is not a result list, and needs its own bound.

    A mesh's `points` is one attribute and megabytes of JSON. Before this existed,
    `explain_value` on a 50,000-point mesh returned 2.83 MB — worse than the whole-stage
    diff the list bound was built to prevent.
    """

    def test_a_short_array_passes_through_as_a_list(self):
        assert bounded_value([1, 2, 3]) == [1, 2, 3]

    def test_a_scalar_is_untouched(self):
        assert bounded_value(5.0) == 5.0
        assert bounded_value(None) is None
        assert bounded_value("inherited") == "inherited"

    def test_an_ordinary_mesh_attribute_passes_through_whole(self):
        """The 90th-percentile array in the sweep was 750 elements, about 17 KB."""
        items = [[float(i), float(i), float(i)] for i in range(750)]
        assert bounded_value(items) == items

    def test_a_long_array_becomes_a_dict_that_says_it_was_trimmed(self):
        """A dict, not a shorter list: a shorter list reads as the whole value."""
        result = bounded_value(list(range(200)), budget=50)
        reported = result["elements_truncated"]["reported"]
        assert 0 < reported < 200
        assert result["elements"] == list(range(reported))
        assert result["elements_truncated"]["total"] == 200

    def test_a_huge_value_is_bounded(self, monkeypatch, bulky):
        """One `points` attribute in usd-wg/assets is 15.1 MB — this is that shape."""
        monkeypatch.setattr(common, "MAX_VALUE_BYTES", 100)
        result = explain_value(bulky[0], "/Mesh", "points")
        assert result["resolved_value"]["elements_truncated"]["total"] == 200
        assert 0 < len(result["resolved_value"]["elements"]) < 200

    def test_the_losing_opinions_value_is_bounded_too(self, tight_values, bulky):
        opinion = explain_value(bulky[0], "/Mesh", "points")["authored_opinions"][0]
        assert opinion["value"]["elements_truncated"]["total"] == 200

    def test_the_whole_result_is_small(self, bulky, lowered_limit):
        assert len(json.dumps(explain_value(bulky[0], "/Mesh", "points"))) < 25_000


class TestComparisonStaysExact:
    """`plain()` is never trimmed. Reporting is bounded; comparing is not.

    A diff that compared truncated arrays would call two different meshes identical,
    which costs more than a large answer ever does.
    """

    def test_a_change_past_the_bound_is_still_detected(self, bulky, lowered_limit):
        """The two stages differ only at the last element, far beyond the 50 reported."""
        result = diff_stages(*bulky)
        assert result["identical"] is False
        assert result["counts"]["attributes_changed"] == 1

    def test_but_the_reported_values_are_bounded(self, tight_values, bulky):
        change = diff_stages(*bulky)["attributes_changed"][0]
        assert change["value_a"]["elements_truncated"]["total"] == 200
        assert change["value_b"]["elements_truncated"]["total"] == 200

    def test_a_stage_against_itself_is_still_identical(self, bulky, lowered_limit):
        assert diff_stages(bulky[0], bulky[0])["identical"] is True

    def test_the_diff_result_is_small(self, bulky, lowered_limit):
        assert len(json.dumps(diff_stages(*bulky))) < 25_000


class TestVariantBounds:
    def test_the_variant_list_is_bounded(self, bulky, lowered_limit):
        assert_bounded(explain_variants(bulky[0], "/Switch")["variant_sets"][0], "variants", 60)

    def test_the_selection_itself_survives_the_bound(self, bulky, lowered_limit):
        """The selection is reported whether or not it is among the variants listed."""
        variant_set = explain_variants(bulky[0], "/Switch")["variant_sets"][0]
        assert variant_set["selection"] == "take000"


class TestWriteBounds:
    def test_the_reported_diff_is_bounded(self, tight_values, bulky):
        result = set_attribute(
            bulky[0], "/Mesh", "points", [(0, 0, 0)] * 200, bulky[0], confirm=False
        )
        assert result["change"]["from"]["elements_truncated"]["total"] == 200
        assert result["change"]["to"]["elements_truncated"]["total"] == 200

    def test_the_explanation_names_the_array_rather_than_spelling_it(self, bulky, lowered_limit):
        """Prose built from a 50,000-element array reproduces the overrun it avoids."""
        result = set_attribute(
            bulky[0], "/Mesh", "points", [(0, 0, 0)] * 200, bulky[0], confirm=False
        )
        assert len(result["explanation"]) < 1000

    def test_the_audit_log_keeps_every_element(self, bulky, tmp_path, monkeypatch):
        """The result is bounded; the record is not. A partial record records nothing."""
        log = tmp_path / "audit.log"
        monkeypatch.setenv("USD_MCP_AUDIT_LOG", str(log))
        set_attribute(
            bulky[0], "/Mesh", "points", [(1, 1, 1)] * 200, bulky[0], confirm=True
        )
        entry = json.loads(log.read_text().splitlines()[-1])
        assert len(entry["to"]) == 200


class TestValueBrief:
    def test_a_scalar_reads_as_itself(self):
        assert value_brief(5.0) == "5.0"

    def test_a_long_array_is_named_by_its_length(self, tight_values):
        assert value_brief(list(range(200))) == "an array of 200 values"

    def test_it_reads_an_already_bounded_value(self, tight_values):
        """Explanations are built from the same dict the result reports."""
        assert value_brief(bounded_value(list(range(200)))) == "an array of 200 values"


class TestTheListLimitDoesNotReachRealWork:
    """The list limit is set above what production assets produce, and must stay there.

    Swept across 466 stages from `usd-wg/assets` and NVIDIA's Isaac Sim library, no
    result list of any kind exceeded 70 entries: the 99th percentile was 2 authored
    opinions, 5 layers in a layer stack, 10 composition arcs, 24 materials. A limit that
    trimmed those would be answering a question nobody asked with a fraction of the
    answer they did.

    These fixtures stand in for that shape — deeper than an average asset, far below the
    limit — and every one of them must come back whole. A limit lowered to where it
    starts trimming ordinary composition fails here, which is the point.
    """

    def _untruncated(self, result):
        return [key for key in result if key.endswith("_truncated")]

    def test_a_layered_shot_reports_every_opinion(self, shot):
        assert self._untruncated(explain_value(shot, "/World/Ball", "radius")) == []

    def test_a_referenced_prim_reports_every_arc(self, composed):
        assert self._untruncated(explain_prim(composed, "/Set/PropA")) == []

    def test_a_variant_set_is_reported_whole(self, composed):
        result = explain_variants(composed, "/Set/PropA")
        assert self._untruncated(result) == []
        assert self._untruncated(result["variant_sets"][0]) == []

    def test_a_profiled_stage_reports_every_layer(self, profiled):
        assert self._untruncated(profile_stage(profiled)) == []

    def test_a_material_library_is_reported_whole(self, looks):
        assert self._untruncated(check_portability(looks, "renderman")) == []

    def test_a_sixty_layer_stage_is_still_under_the_limit(self, wide):
        """Sixty layers and sixty materials — deeper than the sweep's worst, still whole."""
        assert self._untruncated(profile_stage(wide[0])) == []
        assert self._untruncated(check_portability(wide[0], "preview")) == []
        assert self._untruncated(explain_value(wide[0], "/World/Contested", "size")) == []


def test_bounded_plain_matches_converting_then_bounding():
    """`bounded_plain` is `bounded_value(plain(...))` without the discarded conversions.

    The point of the helper is that it never builds the elements the budget drops —
    a 713,718-element `points` array cost 11.3 s to convert and 25.8 ms to sample. It
    is only worth having if what it reports is identical, so this pins the equivalence
    across every shape `plain` dispatches on rather than only the array it optimises.
    """
    from pxr import Gf, Sdf, Vt

    from usd_mcp.common import bounded_plain, plain

    cases = [
        None,
        5.0,
        "hello",
        Sdf.AssetPath("./tex/diffuse.exr"),
        Gf.Vec3f(1, 2, 3),
        Vt.Vec3fArray([]),
        Vt.Vec3fArray([Gf.Vec3f(i, 0, 1.5) for i in range(50)]),
        Vt.Vec3fArray([Gf.Vec3f(i, 0, 1.5) for i in range(40_000)]),
        Vt.TokenArray(["a"] * 40_000),
    ]
    for raw in cases:
        assert bounded_plain(raw) == bounded_value(plain(raw))


def test_bounded_plain_converts_only_what_it_reports(monkeypatch):
    """The saving is the whole reason the helper exists, so it is counted, not assumed.

    Counting conversions is what distinguishes this from the equivalence test above:
    `bounded_value(plain(raw))` returns exactly the same answer and converts every one
    of the 200,000 elements to do it. Only a call count can tell the two apart, so the
    earlier version of this test — which built a counter and then never attached it —
    passed against the implementation it was written to rule out.
    """
    from pxr import Vt

    from usd_mcp import common

    converted = []
    real_plain = common.plain

    def counting_plain(value):
        converted.append(1)
        return real_plain(value)

    monkeypatch.setattr(common, "plain", counting_plain)

    big = Vt.DoubleArray([float(index) for index in range(200_000)])
    result = common.bounded_plain(big)

    reported = result["elements_truncated"]["reported"]
    assert result["elements_truncated"]["total"] == 200_000
    assert 0 < reported < 200_000

    # One conversion per element reported, and none for the 199,000-odd it dropped.
    assert len(converted) <= reported + 1, (
        f"converted {len(converted)} elements to report {reported}; "
        f"the whole array is being converted before the bound trims it"
    )
