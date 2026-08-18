stale

## Summary

`usd_mcp` v0.2.0 is feature-complete and pushed: nine read-only tools, three opt-in
mutating tools, 199 tests at 97% coverage, CI green on 3.10–3.12. Not published to PyPI.

The open work is no longer about building USD features. It is about **repositioning**.
A market assessment concluded the original audience — VFX facilities — is the wrong
target, and that the real audience is *anyone pointing an AI agent at a USD scene*, with
robotics and simulation as the strongest lead. The four todos below are what that
repositioning costs.

## Todos

### Parallel

- [ ] #1 Bound every result payload. On a 200-layer/10,000-prim stage, `diff_stages`
      returns 1.48 MB (~370k tokens) and `profile_stage` returns 78 KB (~20k tokens).
      That overruns an agent's context window and takes the loop down with it; real
      robotics and geospatial scenes are 10–100× larger. Every list-returning field
      (`attributes_changed`, `layers`, `materials`, `shaders`, `authored_opinions`) needs
      a bound plus a reported/total count — the same honesty `counts.within_tolerance`
      already applies to tolerance, applied to truncation. No silent caps. This is the
      one blocker that makes the tool unusable by an agent today.
- [ ] #2 Add a CLI front end over the existing functions — `usd-explain <command>`.
      1,715 lines of USD logic already import nothing from `mcp`, and seven of nine test
      files call the functions directly, so this is a second front door rather than a
      refactor. Roughly a day. Keep the MCP layer; both share the same core.
- [ ] #4 Rewrite the README's opening in symptom language. It currently sells to VFX
      facilities in USD vocabulary. Forum searches for `"which layer wins"`,
      `"composition arc"`, and `"sublayer strength"` return zero or near-zero hits —
      users write "ghost geometry", "geometry won't go away", "always green". The current
      wording is invisible to the people with the problem.

### Sequential

- [ ] #3 (needs: #1, #2) Answer IsaacLab discussion #6508 using CLI output.
      https://github.com/isaac-sim/IsaacLab/discussions/6508 — a user cannot inspect
      geometry reached through an instanceable reference. Posted 2026-07-14, still zero
      replies. It is verbatim the `explain_prim` use case. This is the cheapest real
      demand test available: one afternoon, and a real person either finds it useful or
      does not. Do not post before #1 lands.

## Context

**Read `CLAUDE.md` first** — layout, conventions, the USD gotchas ledger, and where the
real test assets come from. Not duplicated here.

**Environment and CI gate.** No `pxr` in stock Python.
```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check usd_mcp/ tests/
.venv/bin/python -m pytest --cov=usd_mcp --cov-fail-under=90
```

**The strategic verdict: continue, but reposition.** The differentiator is verified by
measurement, not assertion. Six competing USD agent tools were cloned and swept for the
USD APIs that are the only way to answer "which opinion won": `PrimCompositionQuery`,
`GetPropertyStack`, `MakeResolveTargetStrongerThan`, `Usd.AttributeQuery`,
`GetResolveInfo`, any `Pcp` symbol. **Combined hit count across all six: one**, in a test
file, in a one-star repo. What the field ships is inventory — "a layer stack exists" —
never adjudication. Collateral finding: 36 plain `stage.Traverse()` calls across those
repos and zero `TraverseInstanceProxies`, so every competitor silently skips instance
proxies. The accumulated correctness knowledge is the durable asset, not the feature list.

**The NVIDIA opening.** `NVIDIA/skills` ships an `omniverse-usd-performance-tuning` skill
whose `composition-audit.md:37` reads: *"If no safe edit target is obvious, hand off to
`usd-edit-target-planner` instead of guessing."* That planner is pure Markdown and its own
README says it *"does not validate or mutate USD."* NVIDIA also published
`audit-report.schema.json`, whose `composition` object contains `usedLayers`, `sublayers`,
`references`, `payloads`, `variants`, `instanceablePrims`, `unresolvedAssetPaths` — and no
field for a winning layer, strength order, or edit-target verdict. They specified the tool
and shipped a checklist where the implementation goes.

**Reachability.** The `NVIDIA/skills` catalog is closed to outside contributions (one
external contributor ever, a dead-link fix; fork PRs are CI-rejected). The open routes are
the NVIDIA Isaac Sim forum (category 69), IsaacLab's Show & Tell discussions, and a
Community Project Highlights listing via `OmniverseCommunity@nvidia.com`. Precedent: an
outsider posted an Isaac MCP server to category 69, staff thanked them within a day, and
the repo became entry #1 on NVIDIA's official Highlights page. Forum topics auto-close 14
days after the last reply.

**What is *not* differentiated.** NVIDIA's `profile-stage` measures cold/warm stage open,
traversal, attribute resolution, transform computation, and material-binding resolution —
near feature-for-feature with `profile_stage`. Do not lead with that tool.

**Which tools lead for this audience.** Isaac Lab's own USD authoring is shallow: 3 files
use references, 3 use variants, zero use payloads, sublayers, or edit targets, and it does
no composition introspection. But zero USD assets live in its repo (all remote on Nucleus)
and 72 files touch instancing against only 3 using `TraverseInstanceProxies`. The pain
arrives through *consumed* assets, so `explain_prim` (arcs plus instancing) and
`resolve_path` are the entry point; `explain_edit_target` stays the differentiator but is
not the hook. Corroborating reports: IsaacLab issue #5085 (the MJCF importer emits
payload/variant composition arcs their contact sensors cannot resolve through) and a forum
thread where an NVIDIA engineer took thirteen days to answer "which layer won"
(forums.developer.nvidia.com/t/273104 — the cause was a muted layer, and mutedness does not
persist through referencing or payloading).

**Rust was considered and rejected.** Measured split on a realistic stage: ~66 ms inside
USD's C++ engine, ~0.04 ms in Python. A rewrite optimises the 0.04 ms. Bindings exist
(`rust-usd`, `pxr_rs`, `vfx-rs/usd-bind`, and a native `openusd` reimplementation), so it
is possible — it just costs 199 passing tests and weeks for no measurable gain, in a
domain that is overwhelmingly Python. Revisit only if this must run where Python cannot.

**Deferred, not concluded.** Two research threads were cut short rather than answered: a
deeper survey of Isaac Sim's remote USD assets, and the MCP registry/directory landscape.

**Open design question with no decision yet.** Robotics and geospatial assets live behind
custom `Ar` resolvers (`omniverse://`, S3, HTTP). Today `resolve_path` would report valid
assets as unresolvable. Wiring a resolver in collides with safety-contract items 1 (no
network egress) and 8 (no code loaded from disk at runtime). This needs a stated position
before more code is written, because "does this ever touch the network" decides whether the
contract survives this audience. Also unbuilt and relevant: `UsdPhysics` support — the
package touches only `UsdGeom` and `UsdShade`, and physics is where robotics' equivalent
failures live.

## Next Step

Start with #1. Nothing else matters if the first real `diff_stages` call on a production
stage returns 370k tokens; it is also the only item that blocks the public demand test in
#3. Reproduce the numbers first by generating a large synthetic stage (200 layers ×
50 prims) and timing `diff_stages` and `profile_stage` against it, so the fix has a
regression test with real figures behind it.

/home/menser/Dropbox/ai/code/usd_mcp_master
