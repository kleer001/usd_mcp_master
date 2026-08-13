#!/usr/bin/env python
"""MCP entry point. Serves the composition explainers over stdio.

Read-only by construction: no tool here opens a layer for edit, and the server
makes no network calls. Stage paths resolve against the filesystem the server
runs on.
"""

import sys
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from usd_mcp.explain import explain_value as _explain_value
from usd_mcp.explain import why_not_visible as _why_not_visible

server = MCPServer(
    name="usd-mcp",
    version="0.1.0",
    instructions=(
        "Explains OpenUSD composition on local stages. Read-only: it never edits a "
        "layer and never leaves the machine."
    ),
)

# read_only_hint is the machine-readable half of the safety posture in SPEC.md;
# open_world_hint=False says the answer depends only on the local filesystem.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False, idempotent_hint=True)


@server.tool(annotations=READ_ONLY)
def explain_value(
    stage_path: str, prim_path: str, attribute_name: str, time_code: float | None = None
) -> dict[str, Any]:
    """Explain why a USD attribute resolves to the value it does.

    Returns every authored opinion in strength order — strongest first — with the
    layer that authored it and the value it holds, so a losing override can be read
    against the opinion that beat it.

    Args:
        stage_path: path to a .usd/.usda/.usdc/.usdz file.
        prim_path: absolute prim path, e.g. /World/Set/Chair.
        attribute_name: attribute name, e.g. "radius" or "primvars:displayColor".
        time_code: sample a specific frame; omit for the default time code.
    """
    return _explain_value(stage_path, prim_path, attribute_name, time_code)


@server.tool(annotations=READ_ONLY)
def why_not_visible(stage_path: str, prim_path: str) -> dict[str, Any]:
    """Explain why a prim does not appear: missing, deactivated, invisible, or
    excluded by purpose.

    Args:
        stage_path: path to a .usd/.usda/.usdc/.usdz file.
        prim_path: absolute prim path, e.g. /World/Set/Chair.
    """
    return _why_not_visible(stage_path, prim_path)


def main():
    server.run()


if __name__ == "__main__":
    sys.exit(main())
