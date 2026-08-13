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

from usd_mcp.server import build_server

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "usd_mcp"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# The complete set of tools that may write. Enabling writes may add these and nothing
# else; see SPEC.md#safety-contract item 2.
MUTATING_TOOLS = {"set_attribute", "set_visibility", "set_active"}

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
# short — nothing in an explainer legitimately calls `.Set()`.
AUTHORING_CALLS = {
    "Save", "Export", "ExportToString", "CreateNew", "CreateIdentifierForNewAsset",
    "ResolveForNewAsset", "CanWriteAssetToPath",
    "SetEditTarget", "Set", "SetDefault", "ClearDefault", "SetInfo", "SetTimeSample",
    "DefinePrim", "CreatePrim", "OverridePrim", "RemovePrim", "CreateAttribute",
    "CreateRelationship", "SetActive", "SetVisibility", "SetSpecifier",
    "MakeVisible", "MakeInvisible", "SetTypeName", "Reload",
}


# Relative to the package, because `tools/write.py` shares a basename with the write
# module and registers tools rather than authoring anything.
WRITE_MODULE = "write.py"


def _modules():
    """Every Python module in the package, parsed, keyed by package-relative path."""
    paths = sorted(PACKAGE_DIR.rglob("*.py"))
    assert paths, f"no modules found under {PACKAGE_DIR}"
    return [
        (p.relative_to(PACKAGE_DIR).as_posix(), ast.parse(p.read_text(encoding="utf-8")))
        for p in paths
    ]


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


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: v if isinstance(v, str) else "")
def test_no_network_egress(path, tree):
    """Contract 1: stage contents never leave the machine."""
    hits = [(mod, line) for mod, line in _imported_roots(tree) if mod in NETWORK_MODULES]
    assert not hits, f"{path} imports a network module: {hits}"


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: v if isinstance(v, str) else "")
def test_no_process_execution(path, tree):
    """Contract 3 and 4: nothing installs, downloads, or updates anything."""
    imports = [(mod, line) for mod, line in _imported_roots(tree) if mod in PROCESS_MODULES]
    assert not imports, f"{path} imports a process module: {imports}"

    calls = [(name, line) for name, line in _called_attributes(tree) if name in PROCESS_CALLS]
    assert not calls, f"{path} launches a process: {calls}"


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: v if isinstance(v, str) else "")
def test_only_the_write_module_authors(path, tree):
    """Contract 2: authoring is confined to `write.py`.

    The guarantee is not that nothing writes — it is that one named file does, so
    "which code can change my stage" has an answer a reviewer can read in a sitting.
    Authoring that appears anywhere else fails here.
    """
    hits = [(name, line) for name, line in _called_attributes(tree) if name in AUTHORING_CALLS]
    if path == WRITE_MODULE:
        assert hits, f"{WRITE_MODULE} authors nothing; the exemption is no longer earned"
        return
    assert not hits, f"{path} calls a USD authoring API outside {WRITE_MODULE}: {hits}"


def test_the_default_server_has_no_write_path():
    """Contract 2: writing is opt-in, and the default server cannot do it.

    Reads the live server rather than the source, so a tool registered without the
    annotation fails here even if it never touches an authoring call.
    """
    tools = asyncio.run(build_server().list_tools())
    assert tools, "server registered no tools"
    for tool in tools:
        annotations = tool.annotations
        assert annotations is not None, f"{tool.name} carries no annotations"
        assert annotations.read_only_hint is True, f"{tool.name} is not annotated read-only"
        assert annotations.open_world_hint is False, f"{tool.name} claims an open world"

    exposed = MUTATING_TOOLS & {tool.name for tool in tools}
    assert not exposed, f"default server exposes a write path: {exposed}"


def test_mutating_tools_are_exactly_the_declared_set():
    """Contract 2: enabling writes adds these three tools and nothing else.

    Pinning the set means a fourth mutating tool cannot arrive quietly — adding one is
    a deliberate edit to this test, in the same commit as the SPEC.md clause it changes.
    """
    tools = asyncio.run(build_server(enable_write=True).list_tools())
    mutating = {tool.name for tool in tools if not tool.annotations.read_only_hint}

    assert mutating == MUTATING_TOOLS, f"undeclared mutating tools: {mutating ^ MUTATING_TOOLS}"
    for tool in tools:
        if tool.name in MUTATING_TOOLS:
            assert tool.annotations.destructive_hint is True, f"{tool.name} is not destructive"


@pytest.mark.parametrize("name", sorted(MUTATING_TOOLS))
def test_every_mutating_tool_gates_on_confirm_and_an_explicit_layer(name):
    """Contract 2: the dry run is the default, and the edit target is never inferred.

    Both are properties of the published schema, so a tool that dropped either would
    still typecheck and still run — this is what makes them checkable.
    """
    tools = {tool.name: tool for tool in asyncio.run(build_server(enable_write=True).list_tools())}
    schema = tools[name].input_schema

    assert "confirm" in schema["properties"], f"{name} has no confirm gate"
    confirm = schema["properties"]["confirm"]
    assert confirm["default"] is False, f"{name} does not default to a dry run"
    assert "confirm" not in schema["required"], f"{name} makes confirm mandatory"

    assert "target_layer" in schema["required"], f"{name} does not demand a target layer"


def test_dependencies_are_released_packages():
    """Contract 6: no fork, no git dependency, no vendored build."""
    text = PYPROJECT.read_text(encoding="utf-8")
    start = text.index("dependencies = [")
    block = text[start : text.index("]", start)]
    for marker in ("git+", "http://", "https://", "file://", " @ "):
        assert marker not in block, f"dependency block names a {marker!r} source: {block!r}"
