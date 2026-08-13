# usd_mcp — working notes

A read-only MCP server that explains OpenUSD composition. Two tools:
`explain_value` and `why_not_visible`. `README.md` is the user-facing description;
`SPEC.md` is the contract — safety posture, tool surface, and the phased roadmap.

## Layout

```
usd_mcp/
  explain.py   pure functions over a stage path; no MCP, no mutation, returns plain dicts
  server.py    MCP entry point; thin wrapper that registers the two tools
tests/
  conftest.py  builds a two-layer stage (shot.usda sublayers base.usda) in tmp_path
  test_explain.py  the explainers, called directly
  test_server.py   the same behaviour through the MCP tool layer
  test_safety_contract.py  parses usd_mcp/ and asserts the SPEC.md safety contract
```

The split matters: `explain.py` knows nothing about MCP, so the logic is testable
without a transport and reusable outside one. Keep new USD logic there and let
`server.py` stay a registration shim.

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
  an error.
- **Plain dicts out.** USD returns C++ types; `_plain()` converts at the boundary so
  results serialise. Extend it rather than converting at call sites.
- Documentation is addressed to humans. No section instructs an agent — that pattern
  is an injection surface and it is called out as a defect in `SPEC.md`.

## MCP SDK

Built against the 2.x SDK, which replaced `FastMCP` with `mcp.server.MCPServer`.
Result fields are snake_case (`is_error`, `structured_content`, `input_schema`). A tool
annotated `-> dict` raises `InvalidSignature`; structured output needs `-> dict[str, Any]`.
