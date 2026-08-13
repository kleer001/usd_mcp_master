#!/usr/bin/env python
"""MCP entry point. Serves the composition explainers over stdio.

Read-only by construction: no tool here opens a layer for edit, and the server
makes no network calls. Stage paths resolve against the filesystem the server
runs on. This module registers; the explaining happens in `explain.py` and
`compose.py`, which know nothing about MCP.
"""

import sys

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from usd_mcp import prompts, resources
from usd_mcp.tools import compose as compose_tools
from usd_mcp.tools import explain as explain_tools

server = MCPServer(
    name="usd-mcp",
    version="0.1.0",
    instructions=(
        "Explains OpenUSD composition on local stages. Read-only: it never edits a "
        "layer and never leaves the machine. Before proposing an edit to a stage, call "
        "explain_edit_target for the layer you mean to author in — USD accepts an edit "
        "that something stronger overrides, reports no error, and changes nothing."
    ),
)

# read_only_hint is the machine-readable half of the safety posture in SPEC.md;
# open_world_hint=False says the answer depends only on the local filesystem.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False, idempotent_hint=True)

explain_tools.register(server, READ_ONLY)
compose_tools.register(server, READ_ONLY)
resources.register(server)
prompts.register(server)


def main():
    server.run()


if __name__ == "__main__":
    sys.exit(main())
