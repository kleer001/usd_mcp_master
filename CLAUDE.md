# usd_mcp — working notes

A read-only MCP server that explains OpenUSD composition, and authors into them when asked: nine read-only
tools, three opt-in mutating tools, two resources, two prompts. `README.md` is the user-facing description; `SPEC.md` is the contract —
safety posture, tool surface, and the phased roadmap.

## Layout

```
usd_mcp/
  common.py    open a stage, demand a prim, convert USD types to plain Python
  explain.py   value and visibility explainers; pure functions over a stage path
  compose.py   arc, variant, and edit-target explainers; likewise pure
  resolve.py   asset-path resolution; the only module that touches Ar
  diff.py      stage comparison with numeric tolerance; composed or per-layer
  profile.py   layer, payload, instancing, and time cost, and the traps they imply
  portability.py  can the destination host read this shading; render contexts
  write.py     the ONLY module that authors; everything else reads
  tools/       registration only, one module per domain, each with register(server, annotations)
  resources.py stage facts as URI templates
  prompts.py   named diagnostic sequences
  server.py    build_server(enable_write=False); registration only, plus argparse
tests/
  conftest.py  builds the stages every test composes against, in tmp_path
  test_explain.py  the value and visibility explainers, called directly
  test_compose.py  the arc, variant, and edit-target explainers, called directly
  test_diff.py     the stage diff, both scopes, called directly
  test_profile.py  the stage profiler and every finding it emits
  test_portability.py  the shading portability check, one verdict per material
  test_cache.py    the opt-in stage cache, and every way it must invalidate
  test_server.py   the same behaviour through the MCP tool layer
  test_resources.py / test_prompts.py  the non-tool surfaces
  test_write.py    the write path, including that a dry run writes nothing
  test_safety_contract.py  parses usd_mcp/ and asserts the SPEC.md safety contract
```

`conftest.py` builds five fixtures: `shot` (a shot layer sublayering an asset layer) for
strength-ordering questions, `composed` (references, a payload, a variant set, and an
instanced prim) for arc questions, and `drifted` (a pair of stages differing by both
float noise and real edits) for the diff, and `profiled` (instancing, a deferred
payload, and animation that never changes) for the profiler, and `looks` (a material
per portability verdict) for the portability check.

The split matters: every module above `tools/` knows nothing about MCP, so the logic is
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
.venv/bin/python -m pytest --cov=usd_mcp --cov-fail-under=90
```

## Conventions

- **Authoring lives in `write.py` and nowhere else.** The safety test allows USD
  authoring calls in that one file and fails the build anywhere else, so a convenience
  `.Set()` slipped into an explainer does not compile past CI. New USD mutation goes
  there or it does not go in.
- **The stage cache is opt-in and validated, not trusted.** `--cache-stages` serves a
  repeated open from memory only when every layer the stage composed from still has
  the mtime it had; a miss drops the whole cache, because USD will not re-read a layer
  another cached stage is still holding. The write path passes `cached=False` — an
  authored stage whose save fails holds an edit no fingerprint can see.
- **Writes are opt-in and the default server has none.** `build_server()` registers no
  mutating tool; `--enable-write` adds exactly three. The write path is absent from the
  tool list rather than disabled inside it, and a test pins that set.
- **The dry run is the default, not a separate tool.** Every mutating function takes
  `confirm=False` and returns the diff without writing. Do not add a mutating path that
  writes on its first call.
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
- **Plain dicts out.** USD returns C++ types; `common.plain()` converts at the boundary
  so results serialise. Extend it rather than converting at call sites. It special-cases
  `Sdf.AssetPath`, whose `str()` is USD source syntax and discards the resolved path.
- Documentation is addressed to humans. No section instructs an agent — that pattern
  is an injection surface and it is called out as a defect in `SPEC.md`.

## Testing against real assets

The fixtures are synthetic and small. Real production assets compose in ways fixtures
do not, and several bugs here were found only by sweeping them. Two sources, neither
vendored into this repo:

- `github.com/usd-wg/assets` — openly licensed. `full_assets/` for varied attribute
  types and broken MaterialX references; `intent-vfx/scenes/` for heavy native
  instancing (hundreds of instances, thousands of proxies per scene).
- Pixar's Kitchen Set, linked from `openusd.org/release/dl_kitchen_set.html` behind an
  EULA for personal, non-commercial testing — read it before downloading. It ships a
  plain and an instanced build of the same scene, ~230 layers, with variant selections
  contested across three layers and six-arc composition chains.

A sweep is worth running against the write path too, on a **copy**: author each
attribute back to its own value and assert nothing raises and every applied mutation
appears in the audit log exactly once.

## USD gotchas worth not rediscovering

- `Stage.Traverse()` **skips instance proxies**. Use `Stage.Traverse(Usd.TraverseInstanceProxies())`
  to reach them. A sweep over real assets that omits this touches no proxy at all, and
  proxies are where several failure modes live.
- `Usd.PrimDefaultPredicate` also demands `PrimIsLoaded`, so the prim *carrying* an
  unloaded payload is skipped along with its absent contents. Drop that clause to count
  payloads.
- Walking `Sdf.PrimSpec.nameChildren` from a layer's root prims misses everything inside
  a variant — variant contents hang off the variant set. `Sdf.Layer.Traverse` reaches
  them, at paths like `/Prop{lod=low}Geom` (no slash before the child).
- An instance proxy has no prim index of its own, so `MakeResolveTargetStrongerThan`
  against one raises `Tf.ErrorException` from inside USD rather than returning anything.
  It also cannot hold an authored opinion in any layer.
- `Usd.AttributeQuery(attr, resolveTarget).Get()` returns the **schema fallback** when
  nothing stronger is authored. Decide strength with `HasAuthoredValue()`, never `Get()`.
- An attribute with time samples and no authored default resolves to its **schema
  fallback** at `Usd.TimeCode.Default()`, not to its first sample. Two stages whose
  animation differs compare equal at default time; the sample series is what differs.
- `UsdShadeMaterial.ComputeSurfaceSource(context)` already falls back to the universal
  context, so a non-null result does not mean the material authored anything for that
  context. Check `GetOutput(f"{context}:surface").HasConnectedSource()` for that. An
  output also exists as soon as anything asks USD for one; only a connected source is
  a provision.
- `str()` of an `Sdf.AssetPath` is USD source syntax (`@path@`) and drops `resolvedPath`.
- USD **will not re-read a layer that is still in memory**. `Stage.Open` picks up an
  external edit only once every reference to the old layer has been dropped and the
  layer has left USD's registry — so holding a stage alive pins the scene description
  it composed from, whatever the file on disk now says. Tool calls that retain nothing
  between them are fresh for this reason, and `common.enable_stage_cache` has to drop
  every cached stage on a miss to stay that way.

## MCP SDK

Built against the 2.x SDK, which replaced `FastMCP` with `mcp.server.MCPServer`.
Result fields are snake_case (`is_error`, `structured_content`, `input_schema`,
`uri_template`). A tool annotated `-> dict` raises `InvalidSignature`; structured output
needs `-> dict[str, Any]`.

An f-string is not a docstring — Python leaves `__doc__` as None, so a tool defined with
one ships with no description at all. Tool docstrings must be plain literals.

`server.call_tool` *raises* `mcp.server.mcpserver.exceptions.ToolError` when the
underlying function raises — it does not return a result with `is_error` set. Tests that
assert on a failing explainer use `pytest.raises`.

Resource templates reject absolute paths in parameters by default
(`ResourceSecurity`). Stage paths are absolute, so `stage_path` is exempted deliberately
in `resources.py`; the reasoning is in `SPEC.md#surface-beyond-tools`.
