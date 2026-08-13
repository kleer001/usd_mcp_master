# usd-mcp

An MCP server that answers the two USD questions nobody's tooling answers:
**why does this attribute have this value**, and **why can't I see this prim**.

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

## Safety

Both tools are annotated `readOnlyHint`, and the posture behind that is in
[SPEC.md](SPEC.md): local-only, no network egress, no self-update, no write path, `pip`
install only, pinned to a released `usd-core`. A facility can read the whole server in
one sitting.

Authoring is the destination, staged behind the explainer rather than ruled out — a
write path that cannot say where an edit lands reproduces the exact failure this server
diagnoses. The three phases and the contract a write path inherits are in
[SPEC.md](SPEC.md#roadmap).

## Development

```
pip install -e ".[dev]"
pytest
```

The tests build a two-layer stage — a shot layer sublayering an asset layer — and assert
against real composition, not mocks.

## License

MIT
