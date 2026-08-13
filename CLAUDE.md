# usd_mcp — working notes

A read-only MCP server that explains OpenUSD composition: five tools, two resources,
two prompts. `README.md` is the user-facing description; `SPEC.md` is the contract —
safety posture, tool surface, and the phased roadmap.

## Layout

```
usd_mcp/
  common.py    open a stage, demand a prim, convert USD types to plain Python
  explain.py   value and visibility explainers; pure functions over a stage path
  compose.py   arc, variant, and edit-target explainers; likewise pure
  tools/       registration only, one module per domain, each with register(server, annotations)
  resources.py stage facts as URI templates
  prompts.py   named diagnostic sequences
  server.py    MCP entry point; builds the server and calls the register functions
tests/
  conftest.py  builds a two-layer stage (shot.usda sublayers base.usda) in tmp_path
  test_explain.py  the value and visibility explainers, called directly
  test_compose.py  the arc, variant, and edit-target explainers, called directly
  test_server.py   the same behaviour through the MCP tool layer
  test_resources.py / test_prompts.py  the non-tool surfaces
  test_safety_contract.py  parses usd_mcp/ and asserts the SPEC.md safety contract
```

`conftest.py` builds two stages: `shot` (a shot layer sublayering an asset layer) for
strength-ordering questions, and `composed` (references, a payload, a variant set, and an
instanced prim) for arc questions.

The split matters: `explain.py` and `compose.py` know nothing about MCP, so the logic is
testable without a transport and reusable outside one. Keep new USD logic there, put
registration in `tools/`, and let `server.py` stay a list of `register` calls.

## Running the tests

No `pxr` in a stock Python. Make a venv with the real thing:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Tests build real USD layers and assert against real composition. No mocks —
composition is the subject under test, so faking it tests nothing.

CI runs the same gate on 3.10 through 3.12, and adds two checks worth running before
pushing:

```bash
.venv/bin/ruff check usd_mcp/ tests/
.venv/bin/python -m pytest --cov=usd_mcp --cov-fail-under=85
```

## Conventions

- **No write path.** Nothing in this repo opens a layer for edit. Adding one is a
  deliberate phase-3 step with the requirements listed in `SPEC.md#roadmap`, not a
  convenience someone slips into an explainer.
- **No network.** No HTTP client, no telemetry, no update check. Stage contents are
  covered material under a typical VFX NDA and must not leave the machine.
- **The contract is a test, not a promise.** `test_safety_contract.py` fails the build
  on a network import, a process launch, a USD authoring call, or a tool registered
  without `readOnlyHint`. Changing what the server is allowed to do means changing that
  test deliberately, in the same commit as the `SPEC.md` clause it enforces.
- **Fail loudly.** A missing prim or attribute raises `ValueError`. No fallback to a
  near match, no silent empty result — a wrong answer about composition is worse than
  an error. Every way of failing to open a stage surfaces from USD as
  `Tf.ErrorException`; `common.open_stage` translates it so the `ValueError` contract
  holds at the boundary, and that is the only place a USD exception is caught.
- **Plain dicts out.** USD returns C++ types; `_plain()` converts at the boundary so
  results serialise. Extend it rather than converting at call sites.
- Documentation is addressed to humans. No section instructs an agent — that pattern
  is an injection surface and it is called out as a defect in `SPEC.md`.

## MCP SDK

Built against the 2.x SDK, which replaced `FastMCP` with `mcp.server.MCPServer`.
Result fields are snake_case (`is_error`, `structured_content`, `input_schema`,
`uri_template`). A tool annotated `-> dict` raises `InvalidSignature`; structured output
needs `-> dict[str, Any]`.

`server.call_tool` *raises* `mcp.server.mcpserver.exceptions.ToolError` when the
underlying function raises — it does not return a result with `is_error` set. Tests that
assert on a failing explainer use `pytest.raises`.

Resource templates reject absolute paths in parameters by default
(`ResourceSecurity`). Stage paths are absolute, so `stage_path` is exempted deliberately
in `resources.py`; the reasoning is in `SPEC.md#surface-beyond-tools`.
