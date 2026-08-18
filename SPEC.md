# usd-mcp — tool surface and safety contract

## Safety contract

These are constraints on the implementation, not aspirations. Each is checkable by
reading the source, and most are checked by `tests/test_safety_contract.py` on every
run — see **Enforcement** below.

1. **No network egress.** The server imports no HTTP client and calls no remote service.
   Stage contents — prim paths, asset names, layer identifiers — never leave the machine.
   Scene graph contents are covered material under a typical VFX NDA; a tool that
   transmits them is not evaluable regardless of quality.
2. **No write path by default.** `usd-mcp` registers no tool that can author, and
   `usd-explain` registers no command that can. The three mutations exist only when the
   front door is started with `--enable-write`: the write path is *absent from the tool
   list and the command list*, not disabled inside them, so neither a client nor a shell
   can discover or call one. Both doors expose the same three and no more. Authoring is
   confined to `usd_mcp/write.py`; every other module in the package reads. With writes
   enabled, every mutation names its target layer, writes nothing until `confirm=true`,
   and is appended to the audit log.
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

All nine are annotated `readOnlyHint: true`, `openWorldHint: false`, `idempotentHint: true`.
`explain_value` and `why_not_visible` answer what a value resolved to and why a prim is
absent; the three after them answer the questions underneath those — how a prim was
composed at all, and where an edit could land. `resolve_path` and `diff_stages` ask about
files rather than opinions: which one an asset path names, and what changed between two.
`profile_stage` asks what the whole stage costs, and `check_portability` whether
anybody else can read its shading.

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
| `blocked_by` | `null`, `"strength"`, `"read_only_layer"`, or `"instance_proxy"` |
| `target_writable` | whether the layer can be committed to at all |
| `outranked_by` | the layer and value that would beat the edit, or null |
| `value_that_would_survive` | what the attribute would still resolve to, when the edit loses |
| `explanation` | the same finding in a sentence |

`would_win` answers whether an edit would take effect, which needs a writable layer,
enough strength, and a path that can hold an opinion at all. A packaged layer — a `.usdz`, and anything inside one —
accepts an edit in memory and then refuses to save it, so strength is the wrong
question there; reporting it as winning sends a caller to author into a file that
cannot keep the edit. An instance proxy is a third case: it has no prim index of its own, so no layer can hold
an opinion for it — building a resolve target against one raises from inside USD.
`blocked_by` separates the causes.

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

### `diff_stages(stage_a, stage_b, tolerance=0.0, scope="composed")`

What changed between two stages, with numbers compared against a tolerance instead of a
text diff of their serialisations.

| Field | Meaning |
|---|---|
| `identical` | true when nothing differs outside the tolerance |
| `prims_added` / `prims_removed` | prims present in only one of the two, with their type |
| `prims_retyped` | prims in both whose `typeName` differs |
| `attributes_changed[]` | one entry per differing attribute |
| `attributes_changed[].value_a` / `value_b` | the value at default time on each side |
| `attributes_changed[].authored_a` / `authored_b` | false when that side authors no opinion at all, in which case its value is reported as null rather than as the schema fallback |
| `attributes_changed[].time_samples` | null when neither side is animated; otherwise the sample count on each side and the earliest time the two series part |
| `counts.within_tolerance` | differences the tolerance absorbed |

`tolerance` is an absolute bound applied to every number compared — vector and matrix
components, array elements, and time sample times included. Zero is exact equality. The
absorbed differences are counted rather than dropped, because "was this a real edit or a
re-export" is the question being asked and a silent zero would not answer it.

`scope="composed"` opens both stages and compares what they resolve to. It traverses
instance proxies: a change inside an instanced asset lives nowhere else on a composed
stage, and `Stage.Traverse()` skips proxies by default, so a diff built on the default
predicate would report two such stages as identical. `scope="layer"` opens one file each
as authored, without composing, and compares only what that file says — the question
after a re-export, and the one where a prim under a deactivated ancestor still counts.

Attributes are compared at default time and, when either side carries time samples,
sample by sample. An animated attribute with no authored default resolves to its schema
fallback at default time on both sides, so a default-time comparison alone would call two
different curves identical.

Raises `ValueError` on a negative tolerance, an unknown scope, or a file that does not
open.

### `profile_stage(stage_path, load_payloads=True)`

Where a stage's cost sits, and the traps the numbers imply.

| Field | Meaning |
|---|---|
| `layers[]` | every layer the stage uses, heaviest first, session layer excluded |
| `layers[].prim_specs` / `attribute_specs` | what that file authors, composition aside, variant contents included |
| `layers[].time_sampled_specs` | attribute specs in that layer carrying time samples |
| `layers[].constant_time_sampled_specs` | of those, the ones whose every sample holds the same value |
| `prims` | composed counts: total, instance proxies, instances, instanceable, payloads and how many are unloaded |
| `instancing` | prototypes, and `proxy_share` — the fraction of composed prims that are instance proxies |
| `time` | the stage's frame range, whether it is authored at all, and the time sample totals |
| `findings[]` | the traps, in words: constant animation, animation with no frame range, deferred payloads |

Counted from scene description per layer rather than from the composed stage, because
the question is what each file costs to read: a layer contributes its specs whether or
not something stronger overrides them. A variant's contents hang off the variant set
rather than off the prim namespace, and count too — `Sdf.Layer.Traverse` reaches them
where walking `nameChildren` does not.

The composed traversal includes instance proxies and prims whose payload is unloaded.
`UsdPrimDefaultPredicate` demands `PrimIsLoaded` and skips proxies, which between them
hide most of an instanced set and every deferred payload — the two things this tool is
for.

`constant_time_sampled_specs` is the finding worth acting on. An attribute authored with
time samples makes everything downstream of it time-dependent whether or not the samples
differ, so an asset path written once per frame costs a re-cook per frame and buys
nothing. Nothing in USD warns about it, because nothing in USD is wrong.

`load_payloads` must match the session being asked about; a profile with payloads loaded
describes a scene the artist who deferred them is not paying for.

### `check_portability(stage_path, target)`

Whether the destination host can read the stage's shading, per material.

| Field | Meaning |
|---|---|
| `render_context` | the context token `target` resolved to |
| `readable` | true when every material is `native` or `preview_fallback` |
| `materials[].verdict` | `native`, `preview_fallback`, `renderer_specific`, or `unreadable` |
| `materials[].contexts` | every render context the material authors a *connected* terminal output for |
| `materials[].terminals` | per terminal (surface, displacement, volume): what the target resolves, the shaders behind it, and whether it got there by falling back |
| `materials[].terminals[].shaders[].registered_here` | whether this USD build has a plugin defining that shader id |
| `findings[]` | the same verdicts said in words, with the paths |

The four verdicts are four different situations:

- **`native`** — the target's own context has a connected terminal output. The author
  declared this network for this context, so shaders outside the portable set are the
  point rather than a problem.
- **`preview_fallback`** — nothing authored for the target, so it falls back to the
  universal output, which is `UsdPreviewSurface` throughout. It renders, but as a preview
  surface rather than as the look that was authored.
- **`renderer_specific`** — it falls back to a universal output wired outside the
  `UsdPreviewSurface` set. Whether the target reads those shaders depends on plugins this
  cannot see, and a universal output is claiming a portability it may not have.
- **`unreadable`** — nothing resolves for the target at all.

`target` names a render context: a host name (`renderman`, `arnold`, `storm`,
`materialx`, `preview`) or the token itself (`ri`, `arnold`, `glslfx`, `mtlx`,
`universal`). An unrecognised target raises. Each token here was taken from a primary
source — `ri` is `UsdRi.Tokens.renderContext` in USD, `glslfx` appears as
`outputs:glslfx:surface` in USD's render user guide, `arnold` as `outputs:arnold:surface`
in arnold-usd, `mtlx` in USD's MaterialX architecture guide — and passing an unverified
token through would produce a confident answer about a host nobody checked.

`PREVIEW_SURFACE_NODES` is the [UsdPreviewSurface
specification](https://openusd.org/release/spec_usdpreviewsurface.html)'s complete node
set. `test_portability.py` pins it against `Sdr.Registry`, so a node added to the spec
fails the build rather than quietly reading as renderer-specific.

An output exists as soon as anything asks USD for one, so existence is not a provision —
only a connected source is. Networks are walked through their connections rather than by
namespace, so a texture two hops down still counts, and a node graph in the middle is
walked through rather than reported.

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

Three refusals, all `ValueError`: a target layer outside the root layer stack; a packaged
layer, which accepts an edit in memory and then refuses to save it; and a prim that is an
instance proxy, whose opinions USD discards whatever layer they are authored into.

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

`explain.py`, `compose.py`, `diff.py`, `profile.py`, and `portability.py` hold pure
functions over a stage path and know nothing
about MCP. `common.py` holds the three things both do before they can say anything —
open a stage, demand a prim, convert USD's C++ types to Python ones — so they convert at
one boundary rather than each growing its own. Registration lives in
`usd_mcp/tools/<domain>.py`, each module exposing `register(server, annotations)`, with
`resources.py` and `prompts.py` alongside and `server.py` reduced to a list of
`register` calls. Composition logic that a test can call directly, without a server, is
logic a test actually covers.

## Command line

`usd-explain` is a second front door onto the same functions. Every module below the
registration layer imports nothing from `mcp`, so the CLI is not a reimplementation:
`usd-explain value` and the `explain_value` tool call one function and answer
identically. Results are JSON on stdout; a failure is a message on stderr and exit
status 2.

The binary name supplies the verb, so the commands drop it:

| Command | Function |
| --- | --- |
| `usd-explain value STAGE PRIM ATTR [--time-code F]` | `explain_value` |
| `usd-explain why-not-visible STAGE PRIM [--no-payloads]` | `why_not_visible` |
| `usd-explain prim STAGE PRIM` | `explain_prim` |
| `usd-explain variants STAGE PRIM` | `explain_variants` |
| `usd-explain edit-target STAGE PRIM ATTR LAYER` | `explain_edit_target` |
| `usd-explain resolve STAGE ASSET [--anchor-layer L]` | `resolve_path` |
| `usd-explain diff STAGE_A STAGE_B [--tolerance F] [--scope S]` | `diff_stages` |
| `usd-explain profile STAGE [--no-payloads]` | `profile_stage` |
| `usd-explain portability STAGE TARGET` | `check_portability` |
| `usd-explain --enable-write set-attribute STAGE PRIM ATTR VALUE LAYER [--confirm]` | `set_attribute` |
| `usd-explain --enable-write set-visibility STAGE PRIM visible\|invisible LAYER [--confirm]` | `set_visibility` |
| `usd-explain --enable-write set-active STAGE PRIM active\|inactive LAYER [--confirm]` | `set_active` |

`VALUE` is read as JSON so its type is stated rather than guessed: `5` is a number,
`'"red"'` is a string, `[[0, 1, 0]]` is an array of colours. A CLI that inferred the
difference would author the wrong type and report success.

There is no `--cache-stages`. The cache pays for itself across thousands of calls in one
process; a CLI invocation opens one stage and exits.

## Result bounds

The result lists that grow with the size of a stage are trimmed to a **25 KB budget per
field** — roughly six thousand tokens. A result that does not fit in the caller's context
window is not a smaller answer, it is no answer: measured on a 200-layer, 10,000-prim
stage before the bound existed, `diff_stages` returned 1.59 MB and `profile_stage` 78 KB.

The budget is in bytes rather than entries because entries are not the same size.
Measured entries: a layer-stack identifier came to roughly 135 bytes and a profiled layer
250 on a 200-layer synthetic stage, an authored opinion 300, and a material report 913 on
`DrawModes.usd` from `usd-wg/assets`. Exact figures move with path length and scene
content, but the spread does not — the dearest entry costs about seven times the cheapest.
A single entry count lands those at costs differing sevenfold, so it is either too tight
for the cheap fields or too loose for the dear ones. A byte budget lands every field at
the same price and needs no per-field table to keep it there. How many entries that buys
is reported rather than assumed.

**It is set to clear real work by a wide margin.** Swept across stages from the
`usd-wg/assets` collection and NVIDIA's Isaac Sim asset library, the distributions sit far
below it: the 99th percentile was 2 authored opinions, 5 layers in a layer stack, 10
composition arcs, and 24 materials, and the largest list of any kind was 70 entries.

Run over 464 of those stages, `profile_stage` truncated none and `check_portability`
truncated two — the material-heaviest assets in the collection. On `DrawModes.usd`, 27 of
its 70 materials fit the budget, because a material report is the dearest entry the tools
produce. So the budget is not unreachable, and it is not meant to be: it is the point
where an answer stops being worth its cost. It clears ordinary composition questions
entirely, and bites only where a result was going to be large whatever the limit.

The trim is never silent. A list that was trimmed is accompanied by a sibling field
naming what was left out:

```json
"attributes_changed": [ ... 161 entries ... ],
"attributes_changed_truncated": { "reported": 161, "total": 10000 }
```

That key is absent when nothing was dropped, so its presence is the signal. Bounded
fields: `attributes_changed`, `authored_opinions`, `composition_arcs`, `layer_stack`,
`layers`, `materials`, `prims_added`, `prims_removed`, `prims_retyped`,
`root_layer_stack`, `selected_in`, `shaders`, `unportable_shaders`, `variant_sets`,
`variants`.

That list is checked against the source rather than maintained by hand:
`test_safety_contract.py` parses every `bounded()` call in the package and fails the
build if the two disagree. A prose list of field names drifts the moment a field is
added, and a stale list here would be the same species of wrong answer the tools refuse
to give.

Aggregates are never bounded. `diff_stages.counts`, `profile_stage.time`,
`check_portability.summary`, and every `findings` list are computed over everything the
tool examined, not over the slice it reported — a count that counted only what survived
the trim would be the confident wrong answer this server exists to avoid.

**Values as well as lists.** An array is the one value type with no upper size — a
mesh's `points` is a single attribute and megabytes of JSON — so every field carrying an
authored value is bounded too, at **50 elements**: `resolved_value`, an opinion's `value`,
`current_resolved_value`, `value_that_would_survive`, `outranked_by.value`, `diff_stages`'
`value_a` and `value_b`, and the write path's `change.from`, `change.to`, and
`resolved_value_after`.

Arrays are bounded by count rather than by budget because the bound means something
different there. In that same sweep, 22% of authored arrays held more than fifty
elements, the 99th percentile was 61,056, and the largest was 713,718 — one
`faceVertexIndices`. Fifty elements is a sample that shows the shape of the value; nobody
reads the five-hundredth vertex, and bulk geometry is what `usdcat` is for.

A trimmed array becomes a dict rather than a shorter list, because a shorter list reads
as the whole value and nothing in it says otherwise:

```json
"resolved_value": { "elements": [ ... 50 ... ],
                    "elements_truncated": { "reported": 50, "total": 50000 } }
```

Explanations get the same treatment through `value_brief`, which names a long array
(`an array of 50000 values`) rather than spelling it into the prose.

**Where exactness wins instead.** Two paths deliberately keep whole values:

- **Comparison.** `plain()` is never trimmed, and `diff_stages` compares its output
  element by element. Trimming before comparing would report two different meshes as
  identical — a confident wrong answer, which costs more than a large one. Only what the
  diff *reports* is bounded.
- **The audit log.** `write.py` records every element authored. A record of the first
  fifty elements of an edit is not a record of that edit.

Where a list has a meaningful order, it is sorted before it is trimmed, so the bound
drops the least important end: opinions and composition arcs strongest first, profiled
layers by prim specs descending, materials by worst handoff verdict first.

## Stage cache

Off by default; `--cache-stages` turns it on.

Composing a stage is nearly the whole cost of a tool call that reads one prim. On a
200-layer, 10,000-prim stage, opening costs about 66 ms and answering the question
afterwards about 0.04 ms — so a sweep of six thousand calls spends six minutes composing
and a fifth of a second working. One question does not care; a sweep does.

A cached stage is served only when every layer it composed from still has the mtime it
had at composition. Checking that costs under a millisecond against the 66 ms it saves,
so the cache is validated in full rather than trusted. It is bounded by stage count
rather than by bytes, because a production stage's footprint is not knowable in advance.

Two properties keep it opt-in rather than default:

- USD will not re-read a layer it still holds, and a cached stage is what holds it. A
  fingerprint miss therefore drops **every** cached stage, not only the one that moved,
  because stages share layers and a surviving stage would pin the old scene description.
  A stage recomposed from layers nobody released reports the file's old contents with no
  error, which is the failure mode this whole server exists to make impossible.
- A file that did not exist when the stage was composed and does now is invisible to the
  fingerprint. A reference that was broken and is no longer stays broken until the cache
  misses for some other reason.

The write path never takes a cached stage. An authored stage whose save fails holds an
edit no fingerprint can see, and serving that to a reader would report scene description
that is not on disk.

## Roadmap

Authoring is the destination, not a rejected option. It is staged behind the explainer
for a specific reason: USD's characteristic failure is an edit landing in the wrong
layer and silently losing — no error, no warning, a value that simply did not change.
A write path built before the explainer produces that failure faster and cannot account
for it. Built after, every mutation can state where the edit goes and what it will
outrank before it commits.

**Phase 1 — explain (implemented).** `explain_value`, `why_not_visible`, `explain_prim`,
`explain_variants`, `explain_edit_target`, `resolve_path`, `diff_stages`,
`profile_stage`, `check_portability`. The last of these answers where an edit would
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
