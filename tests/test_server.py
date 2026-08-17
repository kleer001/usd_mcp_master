import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from usd_mcp.server import build_server, server


def call(name, **arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    assert not result.is_error, result.content
    return result.structured_content


def test_tools_are_registered_read_only():
    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == {
        "explain_value",
        "why_not_visible",
        "explain_prim",
        "explain_variants",
        "explain_edit_target",
        "resolve_path",
        "diff_stages",
        "profile_stage",
        "check_portability",
    }
    assert all(tool.annotations.read_only_hint for tool in tools)


def test_diff_stages_round_trips_through_the_tool_layer(drifted):
    a, b = drifted
    result = call("diff_stages", stage_a=a, stage_b=b, tolerance=1e-3)

    assert result["counts"]["within_tolerance"] == 2
    assert [c["attribute"] for c in result["attributes_changed"]] == ["primvars:displayColor"]


def test_profile_stage_round_trips_through_the_tool_layer(profiled):
    result = call("profile_stage", stage_path=profiled, load_payloads=False)

    assert result["prims"]["unloaded_payloads"] == 1
    assert any("never changes" in note for note in result["findings"])


def test_check_portability_round_trips_through_the_tool_layer(looks):
    result = call("check_portability", stage_path=looks, target="arnold")

    assert result["render_context"] == "arnold"
    assert result["summary"]["unreadable"] == 2


def test_explain_value_round_trips_through_the_tool_layer(shot):
    result = call(
        "explain_value", stage_path=shot, prim_path="/World/Ball", attribute_name="radius"
    )

    assert result["resolved_value"] == 5
    assert result["authored_opinions"][0]["layer"].endswith("shot.usda")


def test_why_not_visible_round_trips_through_the_tool_layer(shot):
    result = call("why_not_visible", stage_path=shot, prim_path="/World/Hidden/Inner")

    assert result["visible"] is False
    assert "/World/Hidden" in result["reasons"][0]


def test_explain_prim_round_trips_through_the_tool_layer(composed):
    result = call("explain_prim", stage_path=composed, prim_path="/Set/PropA")

    assert [arc["arc_type"] for arc in result["composition_arcs"]] == [
        "root",
        "reference",
        "variant",
    ]


def test_explain_variants_round_trips_through_the_tool_layer(composed):
    result = call("explain_variants", stage_path=composed, prim_path="/Set/PropA")

    assert result["variant_sets"][0]["selection"] == "low"


def test_explain_edit_target_round_trips_through_the_tool_layer(shot, tmp_path):
    result = call(
        "explain_edit_target",
        stage_path=shot,
        prim_path="/World/Ball",
        attribute_name="radius",
        target_layer=str(tmp_path / "base.usda"),
    )

    assert result["would_win"] is False
    assert result["outranked_by"]["layer"].endswith("shot.usda")


def test_a_failing_explainer_surfaces_as_a_tool_error(shot):
    """The explainers raise rather than guess, and the tool layer must not swallow it."""
    with pytest.raises(ToolError, match="no attribute"):
        asyncio.run(
            server.call_tool(
                "explain_value",
                {"stage_path": shot, "prim_path": "/World/Ball", "attribute_name": "nosuchattr"},
            )
        )


def test_resolve_path_round_trips_through_the_tool_layer(composed):
    result = call("resolve_path", stage_path=composed, asset_path="./nosuchfile.usda")

    assert result["resolved"] is False
    assert "does not resolve" in result["explanation"]


def write_call(name, **arguments):
    write_server = build_server(enable_write=True)
    result = asyncio.run(write_server.call_tool(name, arguments))
    assert not result.is_error, result.content
    return result.structured_content


def test_the_default_server_registers_no_write_tools():
    names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert not names & {"set_attribute", "set_visibility", "set_active"}


def test_enabling_writes_adds_exactly_the_three_mutating_tools():
    default = {tool.name for tool in asyncio.run(server.list_tools())}
    enabled = {tool.name for tool in asyncio.run(build_server(enable_write=True).list_tools())}

    assert enabled - default == {"set_attribute", "set_visibility", "set_active"}


def test_a_dry_run_round_trips_through_the_tool_layer(shot, tmp_path, monkeypatch):
    monkeypatch.setenv("USD_MCP_AUDIT_LOG", str(tmp_path / "audit.log"))
    result = write_call(
        "set_attribute",
        stage_path=shot,
        prim_path="/World/Ball",
        attribute_name="radius",
        value=9.0,
        target_layer=shot,
    )

    assert result["applied"] is False
    assert "Dry run" in result["explanation"]


def test_a_confirmed_write_round_trips_through_the_tool_layer(shot, tmp_path, monkeypatch):
    monkeypatch.setenv("USD_MCP_AUDIT_LOG", str(tmp_path / "audit.log"))
    result = write_call(
        "set_attribute",
        stage_path=shot,
        prim_path="/World/Ball",
        attribute_name="radius",
        value=9.0,
        target_layer=shot,
        confirm=True,
    )

    assert result["applied"] is True
    assert result["resolved_value_after"] == 9.0
