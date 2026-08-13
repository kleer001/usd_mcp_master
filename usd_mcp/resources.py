"""Stage facts offered as resources rather than answered as tool calls.

A client that already knows the stage it cares about can read these without
spending a turn asking. They report nothing the tools could not: same stage, same
filesystem, no question a tool is not already allowed to answer.
"""

from mcp.server.mcpserver.resources.templates import ResourceSecurity
from pxr import UsdGeom

from usd_mcp.common import open_stage, root_layer_stack

# The SDK rejects absolute paths in template parameters by default, which guards a
# server that means to sandbox resources under a root. This one has no such root:
# it reads whatever local stage the caller names, exactly as its tools do, and a
# stage path is absolute by nature. Exempting the parameter grants no reach the
# tool surface does not already have.
STAGE_PATH_IS_A_PATH = ResourceSecurity(exempt_params={"stage_path"})


def register(server):
    @server.resource(
        "usd://stage/{+stage_path}/layer-stack",
        mime_type="text/plain",
        security=STAGE_PATH_IS_A_PATH,
    )
    def layer_stack(stage_path: str) -> str:
        """The stage's root layer stack, strongest first."""
        stage = open_stage(stage_path)
        lines = [
            f"{strength}. {layer.identifier}"
            for strength, layer in enumerate(root_layer_stack(stage))
        ]
        return "Root layer stack, strongest first:\n" + "\n".join(lines)

    @server.resource(
        "usd://stage/{+stage_path}/summary",
        mime_type="text/plain",
        security=STAGE_PATH_IS_A_PATH,
    )
    def summary(stage_path: str) -> str:
        """Default prim, up axis, frame range, and the root prims of a stage."""
        stage = open_stage(stage_path)
        default_prim = stage.GetDefaultPrim()
        roots = [prim.GetName() for prim in stage.GetPseudoRoot().GetChildren()]
        return (
            f"Root layer: {stage.GetRootLayer().identifier}\n"
            f"Default prim: {default_prim.GetPath() if default_prim else 'none authored'}\n"
            f"Up axis: {UsdGeom.GetStageUpAxis(stage)}\n"
            f"Meters per unit: {UsdGeom.GetStageMetersPerUnit(stage)}\n"
            f"Frame range: {stage.GetStartTimeCode()} to {stage.GetEndTimeCode()} "
            f"at {stage.GetTimeCodesPerSecond()} fps\n"
            f"Layers in root stack: {len(root_layer_stack(stage))}\n"
            f"Root prims ({len(roots)}): {', '.join(roots) if roots else 'none'}"
        )
