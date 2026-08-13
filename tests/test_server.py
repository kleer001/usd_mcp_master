import asyncio

from usd_mcp.server import server


def call(name, **arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    assert not result.is_error, result.content
    return result.structured_content


def test_tools_are_registered_read_only():
    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == {"explain_value", "why_not_visible"}
    assert all(tool.annotations.read_only_hint for tool in tools)


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
