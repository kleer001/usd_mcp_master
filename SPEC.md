# usd-mcp — tool surface and safety contract

## Safety contract

These are constraints on the implementation, not aspirations. Each is checkable by
reading the source.

1. **No network egress.** The server imports no HTTP client and calls no remote service.
   Stage contents — prim paths, asset names, layer identifiers — never leave the machine.
   Scene graph contents are covered material under a typical VFX NDA; a tool that
   transmits them is not evaluable regardless of quality.
2. **No write path.** No tool opens a layer for edit. There is no write mode to
   misconfigure and no flag that enables one.
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

Should a write path ever be added, it inherits three requirements from this contract:
read-only remains the default, every mutation offers a dry-run diff first, and every
applied mutation appends to an audit log naming layer, prim, attribute, and prior value.

## Implemented tools

Both are annotated `readOnlyHint: true`, `openWorldHint: false`, `idempotentHint: true`.

### `explain_value(stage_path, prim_path, attribute_name, time_code=None)`

Returns the resolved value plus every authored opinion in strength order.

| Field | Meaning |
|---|---|
| `resolved_value` | what `UsdAttribute.Get()` returns |
| `resolved_from` | the `Usd.ResolveInfo` source kind |
| `authored_opinions[]` | one entry per `SdfPropertySpec` in `GetPropertyStack()`, strongest first |
| `authored_opinions[].layer` | identifier of the layer holding the opinion |
| `authored_opinions[].value` | that opinion's own default value, not the resolved one |
| `authored_opinions[].wins` | true for index 0 only |
| `authored_opinions[].time_samples` | sample count at that path in that layer |
| `layer_stack` | the stage's root layer stack, in strength order |

Raises `ValueError` when the prim or the attribute does not exist. It does not fall back
to a near match.

### `why_not_visible(stage_path, prim_path)`

Returns `visible`, a list of `reasons`, and the `checks` behind them. The causes it
distinguishes:

| Cause | Detected via | Reported as |
|---|---|---|
| Prim never composed | `GetPrimAtPath` invalid | deepest existing ancestor, and where the chain stops |
| Deactivated | `Prim.IsActive()` | the prim, plus the layers authoring `active` |
| Unloaded payload | `HasAuthoredPayloads()` and not `IsLoaded()` | payload contents absent |
| Not imageable | `UsdGeom.Imageable` invalid | the prim's actual type |
| Invisible | `ComputeVisibility()` | every ancestor authoring `visibility=invisible`, root-down, with layers |
| Excluded by purpose | `ComputePurpose()` | the purpose token and why a default pass skips it |

Visibility and purpose inherit down namespace, so the answer is usually authored on an
ancestor rather than the prim asked about. The walk reports the ancestor.

## Not implemented

Candidates that fit the same read-only shape, in the order they'd earn their place:

- `what_would_change_if(layer, edit)` — dry-run an edit and report the prims and
  attributes whose resolved values move. The natural companion to `explain_value`.
- `diff_stages(a, b, tolerance)` — prims added, removed, retyped, and attributes changed,
  composed or per-layer. USD ships `usddiff`, but it `usdcat`s both files and hands the
  text to `diff`; the official docs call it "currently quite primitive" and note it "does
  not do any fuzzy numerical comparison. The slightest precision difference will cause a
  diff" ([USD toolset](https://openusd.org/release/toolset.html)). A re-exported layer with
  float noise is therefore indistinguishable from a real edit.
- `resolve_path(asset_path)` — the resolver used, the anchoring layer, the context, and the
  final file. The documented diagnostic today is `TF_DEBUG=AR_RESOLVER_INIT` and log reading.
- `profile_stage(stage_path)` — time dependencies, prims per layer, payload and instancing
  coverage. SideFX staff have noted that a node time-dependent only to set a file path can
  "end up causing huge amounts of your LOP network to re-cook on every frame"
  ([SideFX forum](https://www.sidefx.com/forum/topic/83026/)); that trap is invisible until
  something is slow.
- `check_portability(stage_path, target)` — which shading nodes the destination host can
  actually read. Renderer-specific shaders survive into USD intact and mean nothing at the
  far end, and nothing warns you before the handoff.
