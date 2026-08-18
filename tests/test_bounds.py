"""The bound on result payload size, and the honesty it is required to keep.

A result an agent cannot fit in its context window is not a smaller answer, it is no
answer. Measured on a 200-layer, 10,000-prim stage before the bound existed,
`diff_stages` returned 1.59 MB and `profile_stage` 78 KB — enough on its own to end the
conversation the question was asked in.

So every list a stage can make arbitrarily long is trimmed. The trim is the easy half.
The half worth testing is that a trimmed list always says it was trimmed, and that the
aggregate counts beside it still count everything: a bound that quietly reports fifty of
ten thousand is a confident wrong answer, which is exactly what this package refuses to
give anywhere else.
"""

import json

import pytest

from usd_mcp.common import MAX_ITEMS, bounded
from usd_mcp.compose import explain_prim
from usd_mcp.diff import diff_stages
from usd_mcp.explain import explain_value
from usd_mcp.portability import _SEVERITY, check_portability
from usd_mcp.profile import profile_stage


def assert_bounded(result, field, total):
    """The field was trimmed to the bound and says so, naming what it left out."""
    assert len(result[field]) == MAX_ITEMS
    assert result[f"{field}_truncated"] == {"reported": MAX_ITEMS, "total": total}


class TestBounded:
    def test_a_short_list_passes_through_whole(self):
        assert bounded("things", [1, 2, 3]) == {"things": [1, 2, 3]}

    def test_a_list_exactly_at_the_bound_is_not_truncated(self):
        items = list(range(MAX_ITEMS))
        assert bounded("things", items) == {"things": items}

    def test_the_truncation_key_is_absent_rather_than_empty(self):
        """Its presence is the signal, so a caller can test for it and nothing else."""
        assert "things_truncated" not in bounded("things", [1, 2, 3])

    def test_a_long_list_keeps_the_front_and_reports_the_whole(self):
        result = bounded("things", list(range(200)), limit=10)
        assert result["things"] == list(range(10))
        assert result["things_truncated"] == {"reported": 10, "total": 200}


class TestDiffBounds:
    def test_every_itemised_list_is_bounded(self, wide):
        result = diff_stages(*wide)
        for field in (
            "prims_added",
            "prims_removed",
            "prims_retyped",
            "attributes_changed",
        ):
            assert_bounded(result, field, 60)

    def test_counts_are_of_everything_not_of_what_was_reported(self, wide):
        """The bound trims the itemisation; it must not trim the arithmetic."""
        result = diff_stages(*wide)
        assert result["counts"]["added"] == 60
        assert result["counts"]["removed"] == 60
        assert result["counts"]["retyped"] == 60
        assert result["counts"]["attributes_changed"] == 60

    def test_a_small_diff_is_reported_whole(self, drifted):
        result = diff_stages(*drifted, tolerance=1e-6)
        assert not any(key.endswith("_truncated") for key in result)

    def test_identical_survives_the_bound(self, wide):
        """`identical` is computed before the trim, so a bounded diff is still not one."""
        assert diff_stages(wide[0], wide[0])["identical"] is True
        assert diff_stages(*wide)["identical"] is False


class TestProfileBounds:
    def test_the_layer_list_and_layer_stack_are_bounded(self, wide):
        result = profile_stage(wide[0])
        assert_bounded(result, "layers", 61)
        assert_bounded(result, "root_layer_stack", 61)

    def test_the_costliest_layers_are_the_ones_kept(self, wide):
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
    def test_the_opinion_stack_and_layer_stack_are_bounded(self, wide):
        result = explain_value(wide[0], "/World/Contested", "size")
        assert_bounded(result, "authored_opinions", 60)
        assert_bounded(result, "layer_stack", 61)

    def test_the_winning_opinion_survives_the_bound(self, wide):
        """Strongest first, so the opinion that decided the value is never the one cut."""
        result = explain_value(wide[0], "/World/Contested", "size")
        assert result["authored_opinions"][0]["wins"] is True
        assert result["authored_opinions"][0]["strength"] == 0

    def test_explain_prim_bounds_its_layer_stack(self, wide):
        assert_bounded(explain_prim(wide[0], "/World/Contested"), "layer_stack", 61)


class TestPortabilityBounds:
    def test_the_material_list_is_bounded(self, wide):
        assert_bounded(check_portability(wide[0], "preview"), "materials", 60)

    def test_the_summary_counts_every_material(self, wide):
        result = check_portability(wide[0], "preview")
        assert result["summary"]["materials"] == 60
        assert result["summary"]["unreadable"] == 60

    def test_the_worst_materials_are_the_ones_kept(self, looks):
        """Sorted worst first, so a bound drops what would have rendered anyway."""
        materials = check_portability(looks, "renderman")["materials"]
        verdicts = [entry["verdict"] for entry in materials]
        assert verdicts == sorted(verdicts, key=lambda v: -_SEVERITY[v])

    def test_findings_read_every_material_not_the_bounded_slice(self, wide):
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
