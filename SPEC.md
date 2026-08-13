# usd-mcp — tool surface and safety contract

## Safety contract

These are constraints on the implementation, not aspirations. Each is checkable by
reading the source, and most are checked by `tests/test_safety_contract.py` on every
run — see **Enforcement** below.

1. **No network egress.** The server imports no HTTP client and calls no remote service.
   Stage contents — prim paths, asset names, layer identifiers — never leave the machine.
   Scene graph contents are covered material under a typical VFX NDA; a tool that
   transmits them is not evaluable regardless of quality.
2. **No write path by default.** `usd-mcp` registers no tool that can author. The three
   mutating tools exist only when the server is started with `--enable-write`: the write
   path is *absent from the tool list*, not disabled inside it, so a client cannot
   discover or call one. Authoring is confined to `usd_mcp/write.py`; every other module
   in the package reads. With writes enabled, every mutation names its target layer,
   writes nothing until `confirm=true`, and is appended to the audit log.
3. **`pip install` only.** No install script, no piped shell, no downloaded binary.
   Facilities run vetted, pinned package repositories precisely so that can't happen.
4. **No self-update.** The server has no update command and no version check. Shows
   freeze tool versions; software that changes itself between two shots on the same
   sequence is a change-control violation before it is a technical risk.
5. **README addressed to humans.** No section of the documentation instructs an agent.
   Repository text that issues commands to an agent is an injection surface.
6. **Pinned, released dependencies.** `mcp` and `usd-core`, both from PyPI. No fork, no
   git dependency, no vendored USD build.
7. **Linux-first.** Developed and tested on Linux, which is what the facilities run.
8. **No code loaded from disk at runtime.** The server has no plugin directory, no
   extension hook, and no path it imports user Python from. A tool surface that grows by
   executing whatever a directory contains cannot state what it does, and the safety
   contract above would describe only the shipped half.

The write path inherits three requirements from this contract, and each is enforced
below: read-only remains the server's default, every mutation offers a dry-run diff
first, and every applied mutation appends to an audit log naming layer, prim, attribute,
prior value, and new value. The audit log is `~/.usd-mcp/audit.log` unless
`USD_MCP_AUDIT_LOG` names another path; it is JSON lines, one per applied mutation.

Two audiences are served by that default rather than one. A facility deploys `usd-mcp`
and the write path does not exist in the process. A freelancer adds a flag.

### Enforcement

Prose a reviewer must trust is worth less than a check that fails the build, so the
contract is executable where it can be. `tests/test_safety_contract.py` parses every
module in `usd_mcp/` and asserts:

| Test | Contract item |
|---|---|
| no import of a socket, HTTP, or mail module | 1 |
| no USD authoring or layer-save call outside `write.py` | 2 |
| the default server registers no tool that is not `readOnlyHint: true` | 2 |
| enabling writes adds exactly three tools, each `destructiveHint: true` | 2 |
| every mutating tool defaults `confirm` to false and requires `target_layer` | 2 |
| no `subprocess`, `os.system`, or other process launch | 3, 4 |
| no dependency naming a git ref, URL, or local path | 6 |

The last three read the live server's published schema rather than the source, so a
mutating tool that dropped its confirm gate or inferred its edit target would still
typecheck, still run, and still fail the build. Pinning the mutating set means a fourth
such tool cannot arrive quietly: adding one is a deliberate edit to that test, in the
same commit as the clause above it changes. These run in CI against Python 3.10 through
3.12 alongside `ruff` and the composition tests.

## Implemented tools

All six are annotated `readOnlyHint: true`, `openWorldHint: false`, `idempotentHint: true`.
`explain_value` and `why_not_visible` answer what a value resolved to and why a prim is
absent; the three below answer the questions underneath those — how a prim was composed
at all, and where an edit could land.

### `explain_value(stage_path, prim_path, attribute_name, time_code=None)`

Returns the resolved value plus every authored opinion in strength order.

| Field | Meaning |
|---|---|
| `resolved_value` | what `UsdAttribute.Get()` returns |
| `resolved_value` (asset-typed) | `{asset_path, resolved_path}`; `resolved_path` is null when the asset does not resolve |
| `resolved_from` | the `Usd.ResolveInfo` source kind |
| `authored_opinions[]` | one entry per `SdfPropertySpec` in `GetPropertyStack()`, strongest first |
| `authored_opinions[].layer` | identifier of the layer holding the opinion |
| `authored_opinions[].value` | that opinion's own default value, not the resolved one |
| `authored_opinions[].wins` | true for index 0 only |
| `authored_opinions[].time_samples` | sample count at that path in that layer |
| `layer_stack` | the stage's root layer stack, in strength order |

Raises `ValueError` when the prim or the attribute does not exist. It does not fall back
to a near match.

An asset-valued attribute reports both halves rather than a string. `str()` of an
`SdfAssetPath` yields USD's source syntax, `@like this@`, and drops the resolved
location — which for a texture or a reference is the fact worth having, and whose
absence is exactly how a broken asset path presents.

### `why_not_visible(stage_path, prim_path)`

Returns `visible`, a list of `reasons`, and the `checks` behind them. The causes it
distinguishes:

| Cause | Detected via | Reported as |
|---|---|---|
| Prim never composed | `GetPrimAtPath` invalid | deepest existing ancestor, and where the chain stops |
| Deactivated | `Prim.IsActive()` | the prim, plus the layers authoring `active` |
| Unloaded payload | `HasAuthoredPayloads()` and not `IsLoaded()` | payload contents absent; requires `load_payloads=False` |
| Not imageable | `UsdGeom.Imageable` invalid | the prim's actual type |
| Invisible | `ComputeVisibility()` | every ancestor authoring `visibility=invisible`, root-down, with layers |
| Excluded by purpose | `ComputePurpose()` | the purpose token and why a default pass skips it |

Visibility and purpose inherit down namespace, so the answer is usually authored on an
ancestor rather than the prim asked about. The walk reports the ancestor.

`load_payloads` must match the session being asked about. A stage opened with payloads
loaded composes their contents, so a prim deferred in the artist's session resolves as
visible here — the right answer to a question nobody asked. Pass `load_payloads=False`
to ask about a session that deferred them.

### `explain_prim(stage_path, prim_path)`

The composition arcs that built a prim, strongest first. `explain_value` names the layer
an opinion sits in; this names how that layer entered the stage, which is what decides
whether an override is expressible from where you are at all.

| Field | Meaning |
|---|---|
| `composition_arcs[].arc_type` | `root`, `reference`, `payload`, `variant`, `inherit`, `specialize`, `relocate` |
| `composition_arcs[].introducing_layer` | the layer that authored the arc |
| `composition_arcs[].target_layer` | the layer the arc composes in |
| `composition_arcs[].target_prim_path` | the path it targets there, e.g. `/Prop{lod=low}` |
| `composition_arcs[].in_root_layer_stack` | whether the arc is authored somewhere locally editable |
| `instancing` | `is_instance`, `is_instance_proxy`, `prototype`, and a note when an edit here would be discarded |

Instancing is reported alongside the arcs because it is the other way an override
vanishes without an error: an opinion authored on an instance proxy is simply dropped.

### `explain_variants(stage_path, prim_path)`

Each variant set on a prim, the selection in force, and every layer authoring a
selection, strongest first. A variant selection is prim metadata and composes like any
other opinion, so an asset's own default can be overridden by a shot — or a shot's
selection can lose to something stronger, silently.

| Field | Meaning |
|---|---|
| `variant_sets[].selection` | the selection actually in force |
| `variant_sets[].variants` | every variant the set offers |
| `variant_sets[].selected_in[]` | one entry per layer authoring a selection, strongest first, `wins` true for the first |

### `explain_edit_target(stage_path, prim_path, attribute_name, target_layer)`

Whether an opinion authored in `target_layer` would win or silently lose. This is the
question the roadmap below stages the whole write path behind, and it is answerable
without authoring anything.

| Field | Meaning |
|---|---|
| `would_win` | whether an opinion authored there would actually take effect |
| `blocked_by` | `null`, `"strength"`, or `"read_only_layer"` |
| `target_writable` | whether the layer can be committed to at all |
| `outranked_by` | the layer and value that would beat the edit, or null |
| `value_that_would_survive` | what the attribute would still resolve to, when the edit loses |
| `explanation` | the same finding in a sentence |

`would_win` answers whether an edit would take effect, which needs both a writable
layer and enough strength. A packaged layer — a `.usdz`, and anything inside one —
accepts an edit in memory and then refuses to save it, so strength is the wrong
question there; reporting it as winning sends a caller to author into a file that
cannot keep the edit. `blocked_by` separates the two causes.

Decided by `Usd.CompositionArc.MakeResolveTargetStrongerThan` and `HasAuthoredValue` —
not by the resolved value, which returns the schema fallback when nothing stronger is
authored and would read as an opinion that does not exist.

`target_layer` must be in the stage's root layer stack. A layer reached through a
reference or a payload composes into a different layer stack, where strength means
something else; the tool raises rather than answer a question it was not asked.

### `resolve_path(stage_path, asset_path, anchor_layer=None)`

Which file an asset path names, and when it names nothing, what was tried. Composition
explains which opinion won; resolution explains whether the file holding it was found —
a different failure with the same symptom, and the one behind "it works on my machine".

| Field | Meaning |
|---|---|
| `resolved_path` | the file the path resolves to, or null |
| `resolved` / `exists` | whether the resolver returned a path, and whether that file is on disk |
| `anchor_layer` | the layer the path was anchored to |
| `resolver` / `resolver_context` | the resolver class in force and the stage's context |
| `identifier` | the identifier the resolver derived before resolving it |

A relative asset path anchors to the layer that authors it — not the stage's root layer
and not the working directory — so `anchor_layer` may be any layer the stage uses, not
only the root layer stack. Anchoring a path authored inside a referenced asset to the
root would answer a question nobody asked.

`Ar.Resolver.CreateIdentifier` is a string operation and is not an authoring call; the
safety contract's denylist names `CreateIdentifierForNewAsset` and `ResolveForNewAsset`,
which are.

## Write tools

Registered only under `--enable-write`, annotated `readOnlyHint: false` and
`destructiveHint: true`, and the only tools in the server so annotated.

### `set_attribute(stage_path, prim_path, attribute_name, value, target_layer, confirm=False)`
### `set_visibility(stage_path, prim_path, visible, target_layer, confirm=False)`
### `set_active(stage_path, prim_path, active, target_layer, confirm=False)`

| Field | Meaning |
|---|---|
| `applied` | whether anything was written; false for every `confirm=false` call |
| `change` | `kind` (attribute or metadata), `name`, `from`, `to` |
| `would_win` / `blocked_by` / `outranked_by` | the `explain_edit_target` verdict for this edit |
| `resolved_value_after` | what the value resolves to once the edit is applied |
| `audit_log` | the path the mutation was recorded to |

`target_layer` is required and never inferred. `set_attribute` overrides an attribute
the prim already has, by authored opinion or by schema; it does not invent properties.
`set_visibility` reports the prim's *computed* visibility afterwards, so authoring
`inherited` under an invisible ancestor reports the prim still invisible rather than
implying it was revealed. `set_active` deactivates a whole subtree — descendants stop
composing rather than becoming hidden.

Two refusals, both `ValueError`: a target layer outside the root layer stack, and a
packaged layer, which accepts an edit in memory and then refuses to save it.

An edit into a layer something stronger overrides is **applied, not refused**. Authoring
a losing opinion is legitimate — correcting an asset that a shot overrides is the
ordinary case — so the edit lands where it was asked to and the result states that the
resolved value did not move. Refusing it would be the tool deciding it knows better;
reporting it as successful would be the silent failure this server exists to end.

## Surface beyond tools

Tools are called; resources and prompts are offered. A read-only server should lean on
the latter two, because most of what a client needs about a stage is context it can pull
once rather than a question it must think to ask.

**Resources.** `usd://stage/{+stage_path}/layer-stack` is the root layer stack in
strength order; `usd://stage/{+stage_path}/summary` is the default prim, up axis, metres
per unit, frame range, and root prims. Both front-load what a client would otherwise
discover by guessing.

The SDK rejects absolute paths in resource template parameters by default, and a stage
path is absolute by nature, so `stage_path` is exempted explicitly. The guard protects a
server that means to confine resources beneath a root directory. This one has no such
root: it reads whatever local stage the caller names, exactly as its tools already do,
so the exemption grants no reach the tool surface does not already have. It is written
as a named constant rather than an inline flag so that a reader meets the reasoning
before the exemption.

**Prompts.** `debug_override` walks an override that is not taking effect through the
tools in the order they most often resolve it, and ends by forbidding a proposed edit
that `explain_edit_target` says would lose. `audit_layer_stack` reviews what a shot layer
actually contributes before publish.

Neither surface may report anything a tool could not. A resource that reached beyond the
stage would be an egress path that never appears in the tool list.

## Module layout

`explain.py` and `compose.py` hold pure functions over a stage path and know nothing
about MCP. `common.py` holds the three things both do before they can say anything —
open a stage, demand a prim, convert USD's C++ types to Python ones — so they convert at
one boundary rather than each growing its own. Registration lives in
`usd_mcp/tools/<domain>.py`, each module exposing `register(server, annotations)`, with
`resources.py` and `prompts.py` alongside and `server.py` reduced to a list of
`register` calls. Composition logic that a test can call directly, without a server, is
logic a test actually covers.

## Roadmap

Authoring is the destination, not a rejected option. It is staged behind the explainer
for a specific reason: USD's characteristic failure is an edit landing in the wrong
layer and silently losing — no error, no warning, a value that simply did not change.
A write path built before the explainer produces that failure faster and cannot account
for it. Built after, every mutation can state where the edit goes and what it will
outrank before it commits.

**Phase 1 — explain (implemented).** `explain_value`, `why_not_visible`, `explain_prim`,
`explain_variants`, `explain_edit_target`, `resolve_path`. The last of these answers where an edit would
land without authoring one, which is most of what phase 2 was for.

**Phase 2 — dry run (absorbed).** A separate `what_would_change_if` was not built.
`explain_edit_target` answers where an edit lands without authoring one, and the default
call to every mutating tool returns that same diff and writes nothing — so the dry run
is what the write tool does rather than a tool beside it that a caller can skip. No
throwaway session layer is involved: nothing is authored to predict the outcome, which
is why the prediction is safe to run against a production stage.

**Phase 3 — write (implemented, opt-in).** `set_attribute`, `set_visibility`,
`set_active`, registered only under `--enable-write`. Each takes an
explicit edit target layer and refuses to infer one — guessing the edit target is the
failure this server exists to diagnose. Each returns the phase 2 diff for what it did,
and appends to the audit log. Read-only stays the default because the server defaults
to it, not because the code cannot write.

That default is structural rather than conventional: every mutating tool takes
`confirm: bool = False` and, while it is false, writes nothing and returns the phase 2
diff — the layer the edit would land in, what it would outrank, and which resolved
values would move. Committing requires a second call with `confirm=True`, which a client
can only make after showing the diff. The dry run is therefore not a separate tool an
agent may skip; it is what the write tool does by default. Mutating tools are annotated
`destructiveHint: true` and are the only tools in the server not annotated read-only.

Standalone USD authoring earns its keep where no DCC is in the loop: headless batch
fixes across many layers, pipeline and TD work, CI, repairing a shot without opening
Houdini. Inside a DCC, an MCP server for that application is the better instrument.

## Not implemented

Diagnostics that fit the read-only shape, in the order they'd earn their place:

- `diff_stages(a, b, tolerance)` — prims added, removed, retyped, and attributes changed,
  composed or per-layer. USD ships `usddiff`, but it `usdcat`s both files and hands the
  text to `diff`; the official docs call it "currently quite primitive" and note it "does
  not do any fuzzy numerical comparison. The slightest precision difference will cause a
  diff" ([USD toolset](https://openusd.org/release/toolset.html)). A re-exported layer with
  float noise is therefore indistinguishable from a real edit.
- `profile_stage(stage_path)` — time dependencies, prims per layer, payload and instancing
  coverage. SideFX staff have noted that a node time-dependent only to set a file path can
  "end up causing huge amounts of your LOP network to re-cook on every frame"
  ([SideFX forum](https://www.sidefx.com/forum/topic/83026/)); that trap is invisible until
  something is slow.
- `check_portability(stage_path, target)` — which shading nodes the destination host can
  actually read. Renderer-specific shaders survive into USD intact and mean nothing at the
  far end, and nothing warns you before the handoff.
