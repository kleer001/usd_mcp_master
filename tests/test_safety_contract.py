"""The safety contract in SPEC.md, executed.

Every claim in `SPEC.md#safety-contract` that a machine can check is checked here, so
the contract fails the build rather than failing a reader's attention. The source tests
parse `usd_mcp/` and no further: the claims are about what this repository does, not
about what its dependencies contain.
"""

import ast
import asyncio
from pathlib import Path

import pytest

from usd_mcp import server as server_module

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "usd_mcp"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Contract 1. Reaching the network needs one of these; none is a false positive in a
# server whose entire job is reading local files.
NETWORK_MODULES = {
    "socket", "ssl", "urllib", "http", "ftplib", "smtplib", "poplib", "imaplib",
    "telnetlib", "xmlrpc", "webbrowser", "requests", "httpx", "aiohttp", "urllib3",
    "websockets", "grpc", "boto3",
}

# Contract 3 and 4. Installing or updating anything from inside the server means
# launching a process.
PROCESS_MODULES = {"subprocess", "multiprocessing", "pty", "popen2", "commands"}
PROCESS_CALLS = {"system", "popen", "execv", "execve", "execl", "execlp", "execvp",
                 "spawnv", "spawnl", "fork", "forkpty"}

# Contract 2. Authoring scene description or committing a layer to disk. `Set` is the
# single call that turns a read into a write, so it is listed even though the name is
# short — nothing in a read-only explainer legitimately calls `.Set()`.
AUTHORING_CALLS = {
    "Save", "Export", "ExportToString", "CreateNew", "CreateIdentifier",
    "SetEditTarget", "Set", "SetDefault", "ClearDefault", "SetInfo", "SetTimeSample",
    "DefinePrim", "CreatePrim", "OverridePrim", "RemovePrim", "CreateAttribute",
    "CreateRelationship", "SetActive", "SetVisibility", "SetSpecifier",
    "MakeVisible", "MakeInvisible", "SetTypeName", "Reload",
}


def _modules():
    """Every Python module in the package, parsed."""
    paths = sorted(PACKAGE_DIR.rglob("*.py"))
    assert paths, f"no modules found under {PACKAGE_DIR}"
    return [(p, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))) for p in paths]


def _imported_roots(tree):
    """Top-level package name of every import, with the line it appears on."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0], node.lineno


def _called_attributes(tree):
    """Name and line of every `something.method(...)` call."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield node.func.attr, node.lineno


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: getattr(v, "name", ""))
def test_no_network_egress(path, tree):
    """Contract 1: stage contents never leave the machine."""
    hits = [(mod, line) for mod, line in _imported_roots(tree) if mod in NETWORK_MODULES]
    assert not hits, f"{path.name} imports a network module: {hits}"


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: getattr(v, "name", ""))
def test_no_process_execution(path, tree):
    """Contract 3 and 4: nothing installs, downloads, or updates anything."""
    imports = [(mod, line) for mod, line in _imported_roots(tree) if mod in PROCESS_MODULES]
    assert not imports, f"{path.name} imports a process module: {imports}"

    calls = [(name, line) for name, line in _called_attributes(tree) if name in PROCESS_CALLS]
    assert not calls, f"{path.name} launches a process: {calls}"


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: getattr(v, "name", ""))
def test_no_write_path(path, tree):
    """Contract 2: no tool authors scene description or saves a layer."""
    hits = [(name, line) for name, line in _called_attributes(tree) if name in AUTHORING_CALLS]
    assert not hits, f"{path.name} calls a USD authoring API: {hits}"


def test_every_tool_is_annotated_read_only():
    """Contract 2, machine-readable half.

    Reads the live server rather than the source, so a tool registered without the
    annotation fails here even if it never touches an authoring call.
    """
    tools = asyncio.run(server_module.server.list_tools())
    assert tools, "server registered no tools"
    for tool in tools:
        annotations = tool.annotations
        assert annotations is not None, f"{tool.name} carries no annotations"
        assert annotations.read_only_hint is True, f"{tool.name} is not annotated read-only"
        assert annotations.open_world_hint is False, f"{tool.name} claims an open world"


def test_dependencies_are_released_packages():
    """Contract 6: no fork, no git dependency, no vendored build."""
    text = PYPROJECT.read_text(encoding="utf-8")
    start = text.index("dependencies = [")
    block = text[start : text.index("]", start)]
    for marker in ("git+", "http://", "https://", "file://", " @ "):
        assert marker not in block, f"dependency block names a {marker!r} source: {block!r}"
