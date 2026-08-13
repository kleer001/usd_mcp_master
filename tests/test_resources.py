import asyncio

from usd_mcp.server import server


def read(uri):
    contents = asyncio.run(server.read_resource(uri))
    return "\n".join(item.content for item in contents)


def templates():
    return {template.uri_template for template in asyncio.run(server.list_resource_templates())}


def test_both_stage_resources_are_offered():
    assert templates() == {
        "usd://stage/{+stage_path}/layer-stack",
        "usd://stage/{+stage_path}/summary",
    }


def test_layer_stack_resource_lists_layers_strongest_first(shot, tmp_path):
    text = read(f"usd://stage/{shot}/layer-stack")

    assert text.index("shot.usda") < text.index("base.usda")


def test_layer_stack_resource_omits_the_session_layer(shot):
    assert "session" not in read(f"usd://stage/{shot}/layer-stack")


def test_summary_resource_reports_stage_metadata(composed):
    text = read(f"usd://stage/{composed}/summary")

    assert "Up axis:" in text
    assert "Frame range:" in text
    assert "Set" in text


def test_an_absolute_stage_path_survives_the_template(shot):
    """The stage path is exempt from the SDK's absolute-path rejection, on purpose."""
    assert shot.startswith("/")
    assert shot in read(f"usd://stage/{shot}/layer-stack")
