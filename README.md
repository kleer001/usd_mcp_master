# usd-mcp

An MCP server that answers the USD questions nobody's tooling answers: **why does this
attribute have this value**, **why can't I see this prim**, **how was this prim composed**,
**which variant am I getting**, and **if I edit this layer, will it even win**.

It is read-only, local-only, and has no network path. It does not edit your layers.

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
  "outranked_by": { "layer": "/shots/010/shot.usda", "value": 5.0 },
  "explanation": "An opinion authored in /assets/ball/base.usda would lose and the resolved value would not change. /shots/010/shot.usda already authors 5.0 and is stronger."
}
```

The target layer must be in the stage's root layer stack. A layer reached through a
reference or payload composes somewhere else, where "stronger" means something different,
so the tool raises instead of guessing.

## Resources and prompts

Two resources let a client pull stage context without spending a tool call:
`usd://stage/{stage_path}/layer-stack` for the layer stack in strength order, and
`usd://stage/{stage_path}/summary` for the default prim, up axis, frame range, and root
prims.

Two prompts name a diagnostic order rather than making you reconstruct it:
`debug_override` for an override that is not taking effect, and `audit_layer_stack` for
reviewing what a shot layer contributes before publish.

## Safety

Every tool is annotated `readOnlyHint`, and the posture behind that is in
[SPEC.md](SPEC.md): local-only, no network egress, no self-update, no write path, no
runtime plugin loading, `pip` install only, pinned to a released `usd-core`. A facility
can read the whole server in one sitting.

Those claims are tests, not promises. `tests/test_safety_contract.py` parses the package
and fails the build on a network import, a process launch, a USD authoring call, a
dependency naming a git ref, or a tool registered without `readOnlyHint`.

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
