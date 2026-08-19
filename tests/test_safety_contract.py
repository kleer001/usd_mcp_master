"""The safety contract in SPEC.md, executed.

Every claim in `SPEC.md#safety-contract` that a machine can check is checked here, so
the contract fails the build rather than failing a reader's attention. The source tests
parse `usd_mcp/` and no further: the claims are about what this repository does, not
about what its dependencies contain.
"""

import argparse
import ast
import asyncio
import re
from pathlib import Path

import pytest

from usd_mcp.cli import build_parser
from usd_mcp.server import build_server

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "usd_mcp"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# The complete set of tools that may write. Enabling writes may add these and nothing
# else; see SPEC.md#safety-contract item 2.
MUTATING_TOOLS = {"set_attribute", "set_visibility", "set_active"}

# The same set as the CLI names it. Two front doors, one write path: a mutating command
# that exists on one and not the other would be a second contract nobody wrote down.
MUTATING_COMMANDS = {"set-attribute", "set-visibility", "set-active"}

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

# Contract 8. Loading code at runtime — a plugin directory, an extension hook, a path
# the server imports user Python from. A tool surface that grows by executing whatever a
# directory contains cannot state what it does.
RUNTIME_IMPORT_MODULES = {"importlib", "imp", "pkgutil", "runpy", "zipimport"}
RUNTIME_IMPORT_CALLS = {
    "exec", "eval", "compile", "__import__",
    "load_module", "exec_module", "spec_from_file_location", "module_from_spec",
    "import_module", "load_source", "load_compiled", "iter_modules", "run_path",
}


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


def _called_names(tree):
    """Name and line of every bare `something(...)` call.

    The forbidden calls do not all arrive through an attribute. `os.system` does, and
    `exec`, `eval`, `compile`, and `__import__` do not — they are builtins, called by
    bare name, and a contract that only walked `ast.Attribute` could not see them at
    all. Checking both is what makes "no code loaded at runtime" a test.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            yield node.func.id, node.lineno


def _calls(tree):
    """Every call this contract can forbid, however it is spelled."""
    yield from _called_attributes(tree)
    yield from _called_names(tree)


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

    calls = [(name, line) for name, line in _calls(tree) if name in PROCESS_CALLS]
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


@pytest.mark.parametrize("path,tree", _modules(), ids=lambda v: v if isinstance(v, str) else "")
def test_no_code_is_loaded_at_runtime(path, tree):
    """Contract 8: no plugin directory, no extension hook, no user Python imported.

    Checked the same way as the network and process contracts, and for the same reason:
    a server that grows a tool surface by executing whatever a directory contains cannot
    state what it does, so the contract above would describe only the shipped half.
    """
    imports = [(mod, line) for mod, line in _imported_roots(tree) if mod in RUNTIME_IMPORT_MODULES]
    assert not imports, f"{path} imports a runtime-import module: {imports}"

    calls = [(name, line) for name, line in _calls(tree) if name in RUNTIME_IMPORT_CALLS]
    assert not calls, f"{path} loads code at runtime: {calls}"


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
        assert annotations.idempotent_hint is True, f"{tool.name} is not annotated idempotent"

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
        assert tool.annotations.idempotent_hint is True, f"{tool.name} is not idempotent"
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


def _cli_commands(enable_write):
    """Every subcommand the CLI registers, by name.

    `argparse` publishes no way to enumerate its own subcommands, so this reaches for
    the action holding them. Private, and worth it: the alternative is a contract that
    trusts the CLI to keep a promise the server has to prove.
    """
    parser = build_parser(enable_write=enable_write)
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices


def test_the_default_cli_has_no_write_path():
    """Contract 2, at the second front door: `usd-explain` registers no write command.

    Absent from the command list rather than refused inside it, exactly as the server's
    tool list is — so `usd-explain set-attribute` is an unrecognised command.
    """
    commands = _cli_commands(enable_write=False)
    assert commands, "CLI registered no commands"
    exposed = MUTATING_COMMANDS & set(commands)
    assert not exposed, f"default CLI exposes a write path: {exposed}"


def test_cli_mutating_commands_are_exactly_the_declared_set():
    """Contract 2: enabling writes adds these three commands and nothing else."""
    added = set(_cli_commands(enable_write=True)) - set(_cli_commands(enable_write=False))
    assert added == MUTATING_COMMANDS, f"undeclared mutating commands: {added ^ MUTATING_COMMANDS}"


def test_both_front_doors_expose_the_same_mutating_set():
    """One write path, named twice. Neither front door may grow a mutation the other lacks."""
    assert {name.replace("-", "_") for name in MUTATING_COMMANDS} == MUTATING_TOOLS


@pytest.mark.parametrize("name", sorted(MUTATING_COMMANDS))
def test_every_cli_mutating_command_gates_on_confirm_and_an_explicit_layer(name):
    """Contract 2: the dry run is the default here too, and the layer is never inferred."""
    actions = {action.dest: action for action in _cli_commands(enable_write=True)[name]._actions}

    assert "confirm" in actions, f"{name} has no confirm gate"
    confirm = actions["confirm"]
    assert confirm.default is False, f"{name} does not default to a dry run"
    assert confirm.option_strings == ["--confirm"], f"{name} makes confirm positional"

    assert "target_layer" in actions, f"{name} does not demand a target layer"
    assert not actions["target_layer"].option_strings, f"{name} makes the target layer optional"


def _bounded_fields(tree):
    """Every field name passed to `bounded()` in one module."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "bounded"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            yield node.args[0].value


def test_spec_lists_exactly_the_fields_the_code_bounds():
    """SPEC.md#result-bounds names every bounded field, and no field it does not bound.

    The list is prose, and prose drifts the moment a field is added. Parsing the package
    for `bounded()` calls and comparing is what keeps the published list honest — a
    reader sizing a context budget against a stale list is being given a wrong answer of
    exactly the kind the tools refuse to give.
    """
    in_code = {field for _, tree in _modules() for field in _bounded_fields(tree)}
    assert in_code, "no bounded() calls found; the parse is broken, not the package"

    spec = (Path(__file__).resolve().parent.parent / "SPEC.md").read_text(encoding="utf-8")
    clause = spec[spec.index("Bounded\nfields:") : spec.index("That list is checked")]
    in_spec = set(re.findall(r"`([a-z_]+)`", clause))

    assert in_spec == in_code, (
        f"SPEC.md and the code disagree about bounded fields. "
        f"Only in SPEC: {sorted(in_spec - in_code)}. Only in code: {sorted(in_code - in_spec)}."
    )


def _value_bounded_fields(tree):
    """Every result field whose value goes through `bounded_value` or `bounded_plain`.

    Two shapes reach one: a key in a dict literal, and a subscript assignment onto a
    plan already built. A field bounded either way is a field a caller can receive a
    trimmed array in, so both count.
    """
    wrappers = {"bounded_value", "bounded_plain"}

    def wrapped(value):
        call = value.body if isinstance(value, ast.IfExp) else value
        return (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in wrappers
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and wrapped(value):
                    yield key.value
        elif isinstance(node, ast.Assign) and wrapped(node.value):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    yield target.slice.value


def test_spec_lists_exactly_the_fields_the_code_bounds_as_values():
    """SPEC.md#result-bounds names every value-bounded field, and no field it does not.

    The sibling check above does this for `bounded()` lists. An array is the field type
    that can overrun a context window on its own, so the list naming which fields can
    come back trimmed is the one a reader is most likely to size a budget against —
    and the one whose drift would cost the most.
    """
    in_code = {field for _, tree in _modules() for field in _value_bounded_fields(tree)}
    assert in_code, "no bounded_value()/bounded_plain() calls found; the parse is broken"

    spec = (Path(__file__).resolve().parent.parent / "SPEC.md").read_text(encoding="utf-8")
    # Matched against whitespace-normalised text: which words a Markdown paragraph
    # wraps on is not part of the contract, and a test that made it part of the contract
    # would fail on a reflow with `substring not found`.
    flat = " ".join(spec.split())
    clause = flat[
        flat.index("Bounded value fields:") : flat.index("That list is checked the same way")
    ]
    in_spec = set(re.findall(r"`([a-z_]+)`", clause))

    assert in_spec == in_code, (
        f"SPEC.md and the code disagree about value-bounded fields. "
        f"Only in SPEC: {sorted(in_spec - in_code)}. Only in code: {sorted(in_code - in_spec)}."
    )
