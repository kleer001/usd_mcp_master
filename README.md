# usd-mcp

An MCP server that answers the USD questions nobody's tooling answers: **why does this
attribute have this value**, **why can't I see this prim**, **how was this prim composed**,
**which variant am I getting**, **if I edit this layer will it even win**, **which file
does this asset path actually name**, **what actually changed between these two
stages**, **why is this stage so expensive**, and **will anyone else's renderer read this
shading**. It can author too, if you ask it to.

It is local-only and has no network path. It is read-only by default: the write path
is absent unless you start it with `--enable-write`.

## Why

USD's defining feature is composition, and its defining frustration is that a sparse
override silently loses to a stronger opinion with no explanation. The documented way
to investigate is to set `TF_DEBUG=PCP_PRIM_INDEX` and read log spew, or to open
`usdview` already knowing where to look and what LIVRPS strength ordering implies.

The answer is mechanically available — `UsdAttribute.GetPropertyStack()` returns every
authored opinion in strength order, and `UsdGeomImageable` computes visibility and
purpose — it is just tedious to assemble by hand. That is exactly the shape of work
worth handing to a tool.

## Install

```
pip install .
```

Requires Python 3.10+. Verified against `usd-core` 26.08 and `mcp` 2.0.0 on Linux.

Register with an MCP client (Claude Code shown):

```
claude mcp add usd-mcp -- usd-mcp
```

## Tools

### `explain_value(stage_path, prim_path, attribute_name, time_code=None)`

Every authored opinion for the attribute, strongest first, each with its layer, its
own value, and whether it wins. A losing override reads directly against the opinion
that beat it.

```jsonc
{
  "prim": "/World/Ball",
  "attribute": "radius",
  "resolved_value": 5.0,
  "resolved_from": "Usd.ResolveInfoSourceDefault",
  "authored_opinions": [
    { "strength": 0, "wins": true,  "layer": "/shots/010/shot.usda", "value": 5.0 },
    { "strength": 1, "wins": false, "layer": "/assets/ball/base.usda", "value": 1.0 }
  ],
  "layer_stack": ["/shots/010/shot.usda", "/assets/ball/base.usda"]
}
```

An asset-valued attribute reports what was authored *and* what it resolves to, since a
null resolved path is how a broken texture or reference presents:

```jsonc
{ "asset_path": "./tex/diffuse.exr", "resolved_path": "/shots/010/tex/diffuse.exr" }
```

### `why_not_visible(stage_path, prim_path)`

Covers the four ways a prim disappears without raising an error: it never composed, an
ancestor is deactivated, `visibility` is authored `invisible` somewhere up the chain, or
`purpose` excludes it from a default render. Each reason names the prim and the layer
responsible.

```jsonc
{
  "prim": "/World/Hidden/Inner",
  "visible": false,
  "reasons": ["visibility=invisible on /World/Hidden — authored in /assets/set/base.usda"],
  "checks": { "exists": true, "active": true, "computed_visibility": "invisible" }
}
```

When the prim does not compose at all, the answer names the deepest path that does and
why the chain stops there.

### `explain_prim(stage_path, prim_path)`

The composition arcs that built the prim, strongest first — reference, payload, variant,
inherit, specialize — each with the layer that introduced it and the layer and path it
targets. `explain_value` tells you which layer an opinion is in; this tells you how that
layer got into your stage, which is what decides whether you can override it from where
you are.

It also reports instancing, because that is the other way an override vanishes with no
error: an opinion authored on an instance proxy is discarded.

```jsonc
{
  "prim": "/Set/PropA",
  "composition_arcs": [
    { "strength": 0, "arc_type": "root",      "target_layer": "/shots/010/shot.usda" },
    { "strength": 1, "arc_type": "reference", "target_layer": "/assets/prop.usda", "target_prim_path": "/Prop" },
    { "strength": 2, "arc_type": "variant",   "target_prim_path": "/Prop{lod=low}" }
  ],
  "instancing": { "is_instance": false, "is_instance_proxy": false, "note": null }
}
```

### `explain_variants(stage_path, prim_path)`

Which variant is selected, what else was on offer, and every layer that authored a
selection — strongest first. A selection composes like any other opinion, so the asset's
own default loses to the shot layer, and a shot layer's choice can lose to something
stronger without saying so.

```jsonc
{
  "variant_sets": [{
    "name": "lod",
    "selection": "low",
    "variants": ["high", "low"],
    "selected_in": [
      { "layer": "/shots/010/shot.usda", "selection": "low",  "wins": true },
      { "layer": "/assets/prop.usda",    "selection": "high", "wins": false }
    ]
  }]
}
```

### `explain_edit_target(stage_path, prim_path, attribute_name, target_layer)`

Ask before you author: would an opinion in this layer win, or lose silently? USD accepts
an edit into a layer that something stronger already overrides, raises no error, and
leaves the value exactly as it was. This is that failure, asked in advance — and it needs
no write path to answer.

```jsonc
{
  "target_layer": "/assets/ball/base.usda",
  "would_win": false,
  "blocked_by": "strength",
  "target_writable": true,
  "outranked_by": { "layer": "/shots/010/shot.usda", "value": 5.0 },
  "explanation": "An opinion authored in /assets/ball/base.usda would lose and the resolved value would not change. /shots/010/shot.usda already authors 5.0 and is stronger."
}
```

The target layer must be in the stage's root layer stack. A layer reached through a
reference or payload composes somewhere else, where "stronger" means something different,
so the tool raises instead of guessing.

Strength is not the only way an edit fails. A `.usdz` accepts an edit in memory and then
refuses to save it, so a packaged layer comes back `blocked_by: "read_only_layer"`. A prim
that is an instance proxy comes back `blocked_by: "instance_proxy"` — no layer can hold an
opinion for it, so USD discards the edit wherever you put it.

### `resolve_path(stage_path, asset_path, anchor_layer=None)`

Which file an asset path actually names — and when it names nothing, the anchoring layer
and resolver context it was looked up through. A relative path resolves against the layer
that authors it, not your working directory, which is why resolving one by hand so often
disagrees with USD. The documented alternative is `TF_DEBUG=AR_RESOLVER_INIT` and reading
log spew.

```jsonc
{
  "asset_path": "./nosuchfile.usda",
  "anchor_layer": "/shots/010/shot.usda",
  "resolver": "DefaultResolver",
  "resolved": false,
  "resolved_path": null,
  "explanation": "./nosuchfile.usda does not resolve. It was anchored at /shots/010/shot.usda and looked up through ..."
}
```

### `diff_stages(stage_a, stage_b, tolerance=0.0, scope="composed")`

What changed between two stages — prims added, removed, retyped, and attributes changed.
USD ships `usddiff`, but it runs both files through `usdcat` and hands the text to `diff`;
the docs call it "currently quite primitive" and note it "does not do any fuzzy numerical
comparison. The slightest precision difference will cause a diff". So a layer re-exported
with float noise reads the same as a layer somebody edited.

Here the tolerance is the argument, and what it absorbed is counted rather than hidden:

```jsonc
{
  "identical": false,
  "tolerance": 0.001,
  "prims_added": [{"path": "/World/Added", "type_name": "Sphere"}],
  "prims_retyped": [{"path": "/World/Prop", "type_name_a": "Sphere", "type_name_b": "Cube"}],
  "attributes_changed": [
    {"prim": "/World/Ball", "attribute": "primvars:displayColor",
     "value_a": [[1, 0, 0]], "value_b": [[0, 1, 0]], "time_samples": null}
  ],
  "counts": {"attributes_changed": 1, "within_tolerance": 42}
}
```

Forty-two differences were noise and one was an edit. `scope="composed"` compares what the
two stages resolve to, instanced geometry included; `scope="layer"` compares only what the
two files themselves author, which is what you want when the stage around them did not
change.

### `profile_stage(stage_path, load_payloads=True)`

Where a stage's cost sits: prim and attribute specs per layer, payload and instancing
coverage, the frame range, and a findings list naming what the numbers imply.

The one worth the tool on its own: an attribute authored with time samples makes
everything downstream of it time-dependent whether or not the samples differ. A texture
path written once per frame at the same value costs a re-cook per frame and buys nothing,
and nothing warns you, because nothing is wrong.

```jsonc
{
  "layers": [
    {"layer": "/assets/chair/chair.usda", "prim_specs": 412, "attribute_specs": 1580,
     "time_sampled_specs": 96, "constant_time_sampled_specs": 94}
  ],
  "prims": {"total": 6214, "instance_proxies": 5980, "with_payload": 12, "unloaded_payloads": 0},
  "instancing": {"prototypes": 8, "proxy_share": 0.9623},
  "findings": [
    "94 attribute specs carry time samples whose value never changes. Each one makes everything downstream of it time-dependent and buys nothing; /assets/chair/chair.usda holds 94 of them."
  ]
}
```

Counts include instance proxies and prims whose payload was never loaded. USD's default
traversal predicate skips both, which between them hide most of an instanced set and every
deferred payload.

### `check_portability(stage_path, target)`

Whether the destination host can read the stage's shading. A renderer-specific shader
survives into USD intact — `PxrSurface` is valid scene description any USD build will
open, parse, and show you in `usdview` as nothing. The failure lands at the far end of a
handoff, on somebody else's schedule.

USD's own answer is the render context: a material carries one terminal output per
context, and a host reads the one it recognises. This asks what your target would
actually resolve.

```jsonc
{
  "render_context": "arnold",
  "readable": false,
  "materials": [
    {"material": "/Looks/Skin", "verdict": "preview_fallback", "contexts": ["", "ri"]},
    {"material": "/Looks/Glass", "verdict": "unreadable", "contexts": ["ri"]}
  ],
  "findings": [
    "1 of 2 materials resolve to nothing at all for arnold. Author a terminal for this context or bind a UsdPreviewSurface network to the universal output before handing the stage over. (/Looks/Glass)"
  ]
}
```

`native` means the target's own context is authored. `preview_fallback` means it renders
as a preview surface rather than as the look you built. `renderer_specific` means the
universal output is wired outside the portable set and only some hosts will read it.
`unreadable` means nothing resolves.

`target` takes a host name — `renderman`, `arnold`, `storm`, `materialx`, `preview` — or
the render context token itself. An unrecognised target raises rather than guess at a
context nobody verified.

## Resources and prompts

Two resources let a client pull stage context without spending a tool call:
`usd://stage/{stage_path}/layer-stack` for the layer stack in strength order, and
`usd://stage/{stage_path}/summary` for the default prim, up axis, frame range, and root
prims.

Two prompts name a diagnostic order rather than making you reconstruct it:
`debug_override` for an override that is not taking effect, and `audit_layer_stack` for
reviewing what a shot layer contributes before publish.

## Writing (opt-in)

The server has no write path unless you ask for one:

```
usd-mcp --enable-write
```

That registers `set_attribute`, `set_visibility`, and `set_active`. Without the flag
they do not exist — they are absent from the tool list, not disabled inside it, so a
client cannot call one by accident.

Every mutating tool takes an explicit `target_layer` and never infers it, and writes
nothing until `confirm=true`:

```jsonc
// set_attribute(..., value: 9.0, target_layer: "/shots/010/shot.usda")  — no confirm
{
  "applied": false,
  "change": { "kind": "attribute", "name": "radius", "from": 5.0, "to": 9.0 },
  "would_win": true,
  "explanation": "Dry run — nothing was written. An opinion authored in /shots/010/shot.usda would win: no layer stronger than it authors this attribute. Call again with confirm=true to author it."
}
```

The dry run is what the tool does by default, so it is not a step an agent can skip.
An edit into a layer that something stronger overrides is applied where you asked and
reported as not having moved the resolved value — correcting an asset a shot overrides
is a real thing to want, and the tool says plainly what did and did not change.

Every applied mutation is appended to `~/.usd-mcp/audit.log` as JSON lines, or wherever
`USD_MCP_AUDIT_LOG` points, naming the layer, prim, attribute, and both values.

## Safety

Every tool is annotated `readOnlyHint`, and the posture behind that is in
[SPEC.md](SPEC.md): local-only, no network egress, no self-update, no write path unless
you ask for one, no runtime plugin loading, `pip` install only, pinned to a released
`usd-core`. A facility can read the whole server in one sitting — and authoring is
confined to a single file, `usd_mcp/write.py`, so "what can change my stage" has a
one-file answer.

Those claims are tests, not promises. `tests/test_safety_contract.py` parses the package
and fails the build on a network import, a process launch, a USD authoring call outside
`write.py`, a dependency naming a git ref, a default server exposing anything not
annotated `readOnlyHint`, or a mutating tool that dropped its `confirm` gate or stopped
demanding an explicit target layer.

Authoring is the destination, staged behind the explainer rather than ruled out — a
write path that cannot say where an edit lands reproduces the exact failure this server
diagnoses. The three phases and the contract a write path inherits are in
[SPEC.md](SPEC.md#roadmap).

## Development

```
pip install -e ".[dev]"
pytest
```

The tests build real stages — a shot layer sublayering an asset layer, and a second one
exercising references, payloads, variants, and instancing — and assert against real
composition, not mocks.

```
ruff check usd_mcp/ tests/
pytest --cov=usd_mcp --cov-fail-under=90
```

## License

MIT
