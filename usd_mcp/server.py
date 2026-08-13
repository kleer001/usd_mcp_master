#!/usr/bin/env python
"""MCP entry point. Serves the composition explainers over stdio.

Read-only by default and by construction: `build_server()` registers no tool that can
author, and the write path is absent from the tool list rather than disabled inside it.
`--enable-write` adds it. The server makes no network calls either way, and stage paths
resolve against the filesystem it runs on.

This module registers; the explaining happens in `explain.py`, `compose.py`, and
`resolve.py`, and the authoring in `write.py`, none of which know anything about MCP.
"""

import argparse
import sys

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from usd_mcp import prompts, resources
from usd_mcp.tools import compose as compose_tools
from usd_mcp.tools import explain as explain_tools
from usd_mcp.tools import resolve as resolve_tools
from usd_mcp.tools import write as write_tools

# read_only_hint is the machine-readable half of the safety posture in SPEC.md;
# open_world_hint=False says the answer depends only on the local filesystem.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False, idempotent_hint=True)

# Mutating tools are the only ones not annotated read-only. Authoring the same value
# twice leaves the same scene description, hence idempotent.
MUTATING = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, open_world_hint=False, idempotent_hint=True
)

READ_ONLY_INSTRUCTIONS = (
    "Explains OpenUSD composition on local stages. Read-only: it never edits a layer "
    "and never leaves the machine. Before proposing an edit to a stage, call "
    "explain_edit_target for the layer you mean to author in — USD accepts an edit that "
    "something stronger overrides, reports no error, and changes nothing."
)

WRITE_INSTRUCTIONS = (
    "Explains OpenUSD composition on local stages and can author into them. Nothing "
    "leaves the machine. The set_ tools write only when called with confirm=true; the "
    "default call writes nothing and returns a diff. Show that diff to the user and get "
    "their agreement before confirming. Every set_ tool needs an explicit target_layer: "
    "choose it with explain_edit_target rather than guessing, because USD accepts an "
    "edit that something stronger overrides, reports no error, and changes nothing."
)


def build_server(enable_write=False):
    """Build the server. Without `enable_write` it has no tool that can author."""
    server = MCPServer(
        name="usd-mcp",
        version="0.1.0",
        instructions=WRITE_INSTRUCTIONS if enable_write else READ_ONLY_INSTRUCTIONS,
    )

    explain_tools.register(server, READ_ONLY)
    compose_tools.register(server, READ_ONLY)
    resolve_tools.register(server, READ_ONLY)
    resources.register(server)
    prompts.register(server)

    if enable_write:
        write_tools.register(server, MUTATING)

    return server


# The default server: read-only, and what `usd-mcp` serves with no arguments.
server = build_server()


def main():
    parser = argparse.ArgumentParser(
        description="Read-only MCP server that explains OpenUSD composition."
    )
    parser.add_argument(
        "--enable-write",
        action="store_true",
        help=(
            "register the mutating tools (set_attribute, set_visibility, set_active). "
            "Off by default: without it the server has no write path at all."
        ),
    )
    args = parser.parse_args()

    (build_server(enable_write=True) if args.enable_write else server).run()


if __name__ == "__main__":
    sys.exit(main())
