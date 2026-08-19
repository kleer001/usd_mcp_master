import asyncio

from usd_mcp.server import build_server, server


def render(name, arguments, srv=server):
    result = asyncio.run(srv.get_prompt(name, arguments))
    return "\n".join(
        message.content.text for message in result.messages if hasattr(message.content, "text")
    )


def test_both_prompts_are_offered():
    names = {prompt.name for prompt in asyncio.run(server.list_prompts())}

    assert names == {"debug_override", "audit_layer_stack"}


def test_debug_override_names_the_tools_in_diagnostic_order(shot):
    text = render(
        "debug_override",
        {"stage_path": shot, "prim_path": "/World/Ball", "attribute_name": "radius"},
    )

    assert text.index("explain_value") < text.index("explain_prim")
    assert text.index("explain_variants") < text.index("explain_edit_target")


def test_debug_override_forbids_proposing_a_losing_edit(shot):
    text = render(
        "debug_override",
        {"stage_path": shot, "prim_path": "/World/Ball", "attribute_name": "radius"},
    )

    assert "would lose" in text


def test_audit_prompt_points_at_the_stage_resources(composed):
    text = render("audit_layer_stack", {"stage_path": composed})

    assert f"usd://stage/{composed}/summary" in text
    assert f"usd://stage/{composed}/layer-stack" in text


def test_the_read_only_prompt_does_not_send_a_client_after_tools_it_lacks(shot):
    """A prompt naming set_attribute on a server without it is a dead end."""
    text = render(
        "debug_override",
        {"stage_path": shot, "prim_path": "/World/Ball", "attribute_name": "radius"},
    )

    assert "set_attribute" not in text
    assert "read-only" in text


def test_the_write_prompt_ends_at_a_confirmed_edit(shot):
    text = render(
        "debug_override",
        {"stage_path": shot, "prim_path": "/World/Ball", "attribute_name": "radius"},
        srv=build_server(enable_write=True),
    )

    assert "set_attribute" in text
    assert "confirm" in text
