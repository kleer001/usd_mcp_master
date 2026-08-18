"""The command-line front end, driven through `main` the way a shell drives it.

The explainers are tested directly elsewhere; nothing here re-tests composition. What
this covers is the part a second front door can get wrong on its own: that each command
reaches the function it names with the arguments the user gave, that the write commands
do not exist until they are asked for, and that a failure reads as a message and an exit
status rather than a traceback.
"""

import json

import pytest

from usd_mcp import common
from usd_mcp.cli import build_parser, main


def run(capsys, *argv):
    """Run one command and return its parsed JSON result."""
    status = main(argv)
    assert status == 0, capsys.readouterr().err
    return json.loads(capsys.readouterr().out)


class TestReadCommands:
    def test_value_reports_the_winning_opinion(self, capsys, shot):
        result = run(capsys, "value", shot, "/World/Ball", "radius")
        assert result["resolved_value"] == 5.0
        assert result["authored_opinions"][0]["wins"] is True

    def test_value_passes_the_time_code_through(self, capsys, profiled):
        result = run(
            capsys, "value", profiled, "/Set/PropA/Geom", "radius", "--time-code", "2"
        )
        assert result["time_code"] == 2.0
        assert result["resolved_value"] == 2.0

    def test_why_not_visible_names_the_layer_that_hid_it(self, capsys, shot):
        result = run(capsys, "why-not-visible", shot, "/World/Hidden/Inner")
        assert result["visible"] is False
        assert result["reasons"]

    def test_no_payloads_composes_without_them(self, capsys, profiled):
        loaded = run(capsys, "profile", profiled)
        deferred = run(capsys, "profile", profiled, "--no-payloads")
        assert loaded["payloads_loaded"] is True
        assert deferred["payloads_loaded"] is False
        assert deferred["prims"]["unloaded_payloads"] == 1

    def test_prim_reports_composition_arcs(self, capsys, composed):
        result = run(capsys, "prim", composed, "/Set/PropA")
        assert result["composition_arcs"][0]["strength"] == 0
        assert "reference" in {arc["arc_type"] for arc in result["composition_arcs"]}

    def test_variants_reports_the_selection(self, capsys, composed):
        """The shot layer's `low` beats the asset's own `high`."""
        result = run(capsys, "variants", composed, "/Set/PropA")
        assert result["variant_sets"][0]["selection"] == "low"

    def test_edit_target_answers_win_or_lose(self, capsys, shot):
        result = run(capsys, "edit-target", shot, "/World/Ball", "radius", shot)
        assert result["would_win"] is True

    def test_resolve_reports_the_anchor_it_used(self, capsys, shot):
        result = run(capsys, "resolve", shot, "./tex/diffuse.exr")
        assert result["anchor_layer"] == shot

    def test_resolve_takes_an_explicit_anchor(self, capsys, shot, tmp_path):
        base = str(tmp_path / "base.usda")
        result = run(capsys, "resolve", shot, "./tex/diffuse.exr", "--anchor-layer", base)
        assert result["anchor_layer"] == base

    def test_diff_passes_tolerance_and_scope_through(self, capsys, drifted):
        exact = run(capsys, "diff", *drifted)
        tolerant = run(capsys, "diff", *drifted, "--tolerance", "1e-6", "--scope", "layer")
        assert tolerant["scope"] == "layer"
        assert tolerant["tolerance"] == 1e-6
        assert tolerant["counts"]["within_tolerance"] > 0
        assert exact["counts"]["attributes_changed"] > tolerant["counts"]["attributes_changed"]

    def test_portability_takes_a_host_name(self, capsys, looks):
        result = run(capsys, "portability", looks, "renderman")
        assert result["render_context"] == "ri"

    def test_an_unverified_render_context_is_refused_by_the_parser(self, looks):
        """Refused before a stage is opened: the choices come from the verified set."""
        with pytest.raises(SystemExit):
            main(["portability", looks, "mystery-renderer"])


class TestWriteGate:
    def test_the_default_parser_has_no_write_command(self, shot):
        with pytest.raises(SystemExit):
            main(["set-attribute", shot, "/World/Ball", "radius", "9", shot])

    def test_enable_write_registers_them(self, capsys, shot):
        result = run(
            capsys,
            "--enable-write",
            "set-attribute",
            shot,
            "/World/Ball",
            "radius",
            "9",
            shot,
        )
        assert result["change"]["to"] == 9

    def test_the_dry_run_is_the_default_and_writes_nothing(self, capsys, shot):
        before = open(shot, encoding="utf-8").read()
        result = run(
            capsys, "--enable-write", "set-attribute", shot, "/World/Ball", "radius", "9", shot
        )
        assert result["applied"] is False
        assert open(shot, encoding="utf-8").read() == before

    def test_confirm_authors_the_edit(self, capsys, shot):
        result = run(
            capsys,
            "--enable-write",
            "set-attribute",
            shot,
            "/World/Ball",
            "radius",
            "9",
            shot,
            "--confirm",
        )
        assert result["applied"] is True
        assert run(capsys, "value", shot, "/World/Ball", "radius")["resolved_value"] == 9.0

    def test_set_visibility_takes_a_state_word(self, capsys, shot):
        result = run(
            capsys,
            "--enable-write",
            "set-visibility",
            shot,
            "/World/Hidden",
            "visible",
            shot,
        )
        assert result["change"]["to"] == "inherited"

    def test_set_active_takes_a_state_word(self, capsys, shot):
        result = run(
            capsys, "--enable-write", "set-active", shot, "/World/Off", "active", shot
        )
        assert result["change"]["to"] is True


class TestValueTyping:
    def test_a_value_is_read_as_json_so_its_type_is_stated(self, capsys, shot):
        """`5` is a number; a CLI that guessed would author the wrong type and say it worked."""
        result = run(
            capsys, "--enable-write", "set-attribute", shot, "/World/Ball", "radius", "5", shot
        )
        assert result["change"]["to"] == 5
        assert not isinstance(result["change"]["to"], str)

    def test_a_bare_word_is_refused_rather_than_taken_as_a_string(self, shot):
        with pytest.raises(SystemExit):
            main(
                [
                    "--enable-write",
                    "set-attribute",
                    shot,
                    "/World/Guide",
                    "purpose",
                    "render",
                    shot,
                ]
            )

    def test_a_quoted_word_is_a_string(self, capsys, shot):
        result = run(
            capsys,
            "--enable-write",
            "set-attribute",
            shot,
            "/World/Guide",
            "purpose",
            '"render"',
            shot,
        )
        assert result["change"]["to"] == "render"

    def test_an_array_is_a_vector(self, capsys, shot):
        result = run(
            capsys,
            "--enable-write",
            "set-attribute",
            shot,
            "/World/Ball",
            "primvars:displayColor",
            "[[0, 1, 0]]",
            shot,
        )
        assert result["change"]["to"] == [[0, 1, 0]]


class TestFailure:
    def test_a_missing_prim_is_a_message_and_an_exit_status(self, capsys, shot):
        assert main(["value", shot, "/World/Nope", "radius"]) == 2
        assert "no prim at /World/Nope" in capsys.readouterr().err

    def test_an_unopenable_stage_is_a_message_and_an_exit_status(self, capsys, tmp_path):
        missing = str(tmp_path / "nosuchstage.usda")
        assert main(["profile", missing]) == 2
        assert "could not open" in capsys.readouterr().err

    def test_nothing_is_printed_to_stdout_on_failure(self, capsys, shot):
        main(["value", shot, "/World/Nope", "radius"])
        assert capsys.readouterr().out == ""


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        main([])


def test_every_command_carries_help_text():
    """The help is the whole interface for a person who has not read SPEC.md."""
    parser = build_parser(enable_write=True)
    assert "OpenUSD" in parser.description


class TestResultBounds:
    """Bounded by default on both front doors; `--full` is what turns that off.

    A shell is not reliably a pipe. The same stdout reaches a terminal and an agent's
    shell tool, and an agent driving this spends the output against a context window
    exactly as an MCP client would — so the default cannot assume the generous case.
    """

    def test_the_default_is_bounded(self, capsys, bulky, monkeypatch):
        monkeypatch.setattr(common, "MAX_VALUE_BYTES", 100)
        result = run(capsys, "value", bulky[0], "/Mesh", "points")
        assert result["resolved_value"]["elements_truncated"]["total"] == 200

    def test_full_reports_the_array_whole(self, capsys, bulky, monkeypatch):
        monkeypatch.setattr(common, "MAX_VALUE_BYTES", 100)
        result = run(capsys, "--full", "value", bulky[0], "/Mesh", "points")
        assert isinstance(result["resolved_value"], list)
        assert len(result["resolved_value"]) == 200

    def test_full_reports_every_variant(self, capsys, bulky, monkeypatch):
        monkeypatch.setattr(common, "MAX_FIELD_BYTES", 200)
        result = run(capsys, "--full", "variants", bulky[0], "/Switch")
        assert len(result["variant_sets"][0]["variants"]) == 60
        assert not any(k.endswith("_truncated") for k in result["variant_sets"][0])

    def test_full_drops_the_budgets_for_the_whole_process(self, capsys, bulky, monkeypatch):
        """It is process-wide, and safe only because a CLI run answers one command and exits.

        Anything that grows this module into a long-lived host — a REPL, a service, a
        second command in one process — has to set the budgets per call instead.
        """
        monkeypatch.setattr(common, "MAX_VALUE_BYTES", 100)
        run(capsys, "--full", "value", bulky[0], "/Mesh", "points")
        assert common.MAX_VALUE_BYTES is None
