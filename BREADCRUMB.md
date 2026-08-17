stale

## Summary

`usd_mcp` — an MCP server that explains OpenUSD composition, and (opt-in) authors into it.
Phases 1–3 of `SPEC.md` are complete and pushed; CI green on Python 3.10/3.11/3.12 with
127 tests at 96% coverage. Working tree clean, `main` level with `origin/main`.

The session built out the surface from two tools to nine, made the safety contract
executable rather than aspirational, and validated everything against real production
assets — which is what found most of the bugs.

Current surface: six read-only tools (`explain_value`, `why_not_visible`, `explain_prim`,
`explain_variants`, `explain_edit_target`, `resolve_path`), three opt-in mutating tools
behind `--enable-write` (`set_attribute`, `set_visibility`, `set_active`), two resources,
two prompts.

## Todos

### Parallel

- [ ] #1 `diff_stages(a, b, tolerance)` — prims added/removed/retyped and attributes
      changed, composed or per-layer. First item on SPEC's "Not implemented" list and the
      highest-value one: `usddiff` just `usdcat`s both files and text-diffs them, so float
      noise from a re-export is indistinguishable from a real edit.
- [ ] #2 `profile_stage(stage_path)` — time dependencies, prims per layer, payload and
      instancing coverage. Targets the trap where a node time-dependent only to set a file
      path re-cooks a whole LOP network every frame.
- [ ] #3 `check_portability(stage_path, target)` — which shading nodes the destination host
      can actually read. Renderer-specific shaders survive into USD intact and mean nothing
      at the far end, with no warning before handoff.
- [ ] #4 Stage-open cost — every tool call re-opens and re-composes the stage. Fine for a
      single call, but an exhaustive sweep over a 6,000-proxy scene does not finish in ten
      minutes. Consider a bounded stage cache keyed on identifier + mtime *if* a real
      workload needs it; do not add it speculatively.
- [ ] #5 Decide whether to publish to PyPI. `pyproject.toml` already carries urls,
      keywords, and classifiers; version is still `0.1.0`.

## Context

**Read `CLAUDE.md` first** — it holds the layout, conventions, the USD gotchas ledger
(traversal skipping instance proxies, resolve-target vs schema fallback, `SdfAssetPath`
stringification, layer-cache freshness), and where to get real test assets. Do not
duplicate that here.

**Environment.** No `pxr` in stock Python. `python3 -m venv .venv && .venv/bin/pip install
-e ".[dev]"`. The CI gate, run exactly as CI runs it:
```
.venv/bin/ruff check usd_mcp/ tests/
.venv/bin/python -m pytest --cov=usd_mcp --cov-fail-under=90
```

**The safety contract is executable.** `tests/test_safety_contract.py` AST-parses
`usd_mcp/` and fails the build on: a network import, a process launch, a USD authoring call
outside `write.py`, a git/URL dependency, a default server exposing a non-read-only tool, an
undeclared fourth mutating tool, or a mutating tool that dropped its `confirm` default or
stopped requiring `target_layer`. Every check was verified to fail against an injected
violation before being kept — hold new checks to that same standard, or they are decoration.
Changing what the server may do means editing that test deliberately, in the same commit as
the `SPEC.md` clause it enforces.

**Write path design (do not erode).** Authoring is confined to `usd_mcp/write.py`; every
other module reads. Writes are opt-in — `build_server()` registers no mutating tool, and
`--enable-write` adds exactly three. The dry run is the default (`confirm=False` returns the
diff and writes nothing), computed by the same `edit_target_verdict` that
`explain_edit_target` uses so the two cannot drift. An edit into a layer something stronger
overrides is **applied, not refused** — correcting an asset a shot overrides is ordinary
work — and the result states plainly that the resolved value did not move.

**`blocked_by` taxonomy:** `null` | `"strength"` | `"read_only_layer"` (packaged/usdz —
accepts an edit in memory then refuses to save) | `"instance_proxy"` (no prim index of its
own; USD discards the opinion whatever layer it lands in). Explain *explains* these; the
write path *refuses* the latter two.

**Audit log:** JSON lines at `~/.usd-mcp/audit.log`, overridable via `USD_MCP_AUDIT_LOG`,
appended before each mutating call returns. Tests must set that env var or they write to
the developer's home.

**Known gap:** none blocking. `SPEC.md`'s phase 2 (`what_would_change_if`) was deliberately
absorbed rather than built — `explain_edit_target` plus the default dry run cover it, and
nothing is authored to predict an outcome, which is why prediction is safe against a
production stage. That reasoning is recorded in the roadmap; don't "restore" phase 2 without
reading it.

## Next Step

Pick up #1, `diff_stages`. It is first on SPEC's not-implemented list in the order those
items "earn their place," and the rationale against `usddiff` is already written there.
Before building it, re-read `SPEC.md#not-implemented` — the tolerance argument is the whole
point of the tool and is easy to get wrong.

/home/menser/Dropbox/ai/code/usd_mcp_master
