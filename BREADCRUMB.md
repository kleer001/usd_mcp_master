fresh

## Summary

`usd_mcp` 0.3.0 is pushed: two front doors (`usd-mcp` over MCP, `usd-explain` as a CLI)
over one core, 289 tests at 97.8% coverage, result bounds measured against production
USD rather than guessed.

The open work is **outreach**. The first real demand test is live — a reply posted
2026-08-18 to IsaacLab discussion #6508, a question that sat 35 days with zero answers.
The todos below are the next lone voices found by the same method, plus one genuinely
open contribution route into NVIDIA's official USD curriculum.

## Todos

### Parallel

- [ ] #1 Answer IsaacLab discussion #4828 — "How to save collision mesh to a
      Blender-exported USD so it persists". Opened 2026-03-05, zero replies. The asker
      adds a collider in the Isaac Sim GUI, it works, and it is gone on reload. That is
      an edit landing in a session layer instead of the asset layer — the single failure
      this package exists to name. `explain_value` on `physics:collisionEnabled` and
      `explain_edit_target` against the asset layer answer it directly.
      https://github.com/isaac-sim/IsaacLab/discussions/4828
- [ ] #2 Answer IsaacLab discussion #5206 — "How to use different HDRI backgrounds per
      environment in parallel environments?". Opened 2026-04-08, zero replies. Per-env
      `DomeLight`s authored under `/World/envs/env_N` and "both environments still appear
      to share the same HDRI, or one overrides the other". Either the env prims are
      instanced (opinions on proxies are discarded) or something stronger wins.
      `explain_prim` reports the instancing, `explain_value` the contest. The asker even
      asks the right question — "Are DomeLights effectively global in Omniverse/USD, even
      if authored under different env paths?" — and nobody answered it.
      https://github.com/isaac-sim/IsaacLab/discussions/5206
- [ ] #3 Investigate IsaacLab discussion #6020 — "Ray Caster isn't working for my Robot".
      Opened 2026-06-07, zero replies. URDF-converted robot; the raycaster works on the
      stock Anymal and not on theirs. Plausibly instanceable meshes the raycaster cannot
      see. Weaker match than #1 and #2 — confirm the mechanism before replying, and drop
      it if instancing is not the cause rather than posting a guess.
      https://github.com/isaac-sim/IsaacLab/discussions/6020

### Sequential

- [ ] #4 (needs: #1, #2) Contribute to `NVIDIA-Omniverse/LearnOpenUSD`. Apache-2.0, 304
      stars, 68 forks, `CONTRIBUTING.md`, and 39 merged PRs across 12 contributors of
      whom 10 are **not** NVIDIA staff — a genuinely open route into NVIDIA's official
      USD curriculum, unlike `NVIDIA/skills`. 141 doc pages. The natural target is
      `docs/asset-modularity-instancing/instancing-faq.md` and the
      `refining-scenegraph-instances/` pages, which is exactly where "my override on an
      instance vanished" lives. Land the forum answers first so the contribution cites
      real questions rather than an invented one.
      https://github.com/NVIDIA-Omniverse/LearnOpenUSD

## Context

**Read `CLAUDE.md` first** — layout, conventions, the USD gotchas ledger, the two-front-
door rule, and where the real test assets come from. Not duplicated here.

**Environment and CI gate.** No `pxr` in stock Python.
```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check usd_mcp/ tests/
.venv/bin/python -m pytest --cov=usd_mcp --cov-fail-under=90
```

**The first demand test is live.** Answered IsaacLab #6508 (DexCube physical dimensions,
posted 2026-07-14, 35 days with zero replies) on 2026-08-18. The answer — 0.06 m per
side — was verified four ways: authored `size` × `xformOp:scale`, `UsdGeom.BBoxCache`,
`physics:mass` over volume landing on exactly 1000 kg/m³, and identical values across
Isaac Sim 4.5 and 5.0. The reply names `usd_mcp` in a closing paragraph, so a reply or
its absence is the signal. Watch for a response before investing further in that channel.
https://github.com/isaac-sim/IsaacLab/discussions/6508#discussioncomment-18069888

**Channel assessment, measured 2026-08-18.** Not all forums are the same shape:

- **IsaacLab discussions** — the productive seam. 66 of the most recent 100 discussions
  have zero replies; 22 of those are USD or composition shaped. This is where the lone
  voices are.
- **AOUSD forum** (`forum.aousd.org`) — well answered and expert-heavy; most topics have
  replies within days, and the unanswered ones are Hydra internals, not "my override
  vanished". Not a lone-voice seam, but a **sharing** venue: the `USDseal Inspector`
  thread shows an outsider's USD inspection tool drawing replies there.
- **NVIDIA Omniverse forum, category 69** — zero of the latest 30 topics unanswered;
  staff respond actively. A sharing venue rather than a place to find unmet need.
- **Stack Overflow** — dead. The `usd` tag is dominated by currency questions and the
  `openusd` / `pixar-usd` tags return nothing.

**Classes and curricula.** `LearnOpenUSD` above is the contribution route. Two more are
audience rather than route: NVIDIA's free DLI OpenUSD courses, which include a *Creating
Composition Arcs* module, and CAVE Academy's *Introduction to OpenUSD*. Both teach the
subject this tool debugs, and neither is contributable.

**Method that found all of this.** Search where the people with the problem actually
ask, filter for **unanswered**, sort by age, and read the words they used rather than the
words the docs use. Recorded as a standing rule in the global `~/.claude/CLAUDE.md`
("Find the Lone Voice in the Forest"). Verify the answer independently before posting; a
wrong answer to a lone voice is worse than silence.

**Posting is the user's call.** Draft, verify, show, ask — never post under their GitHub
account without explicit approval on that specific text.

**Two skills now guard published prose**, both invocable: `honest-copy` (audit for claims
the build does not keep) and `humanized-copy`. `honest-copy` has caught real defects in
this repo's own README and SPEC twice, including numbers written from estimate rather
than measurement. Run it on any reply, README change, or contribution before it ships.

**Deferred, not concluded.** Two research threads remain open from earlier work: a deeper
survey of Isaac Sim's remote USD assets, and the MCP registry/directory landscape.

**Open design question, still undecided.** Robotics and geospatial assets live behind
custom `Ar` resolvers (`omniverse://`, S3, HTTP). Today `resolve_path` reports such
assets as unresolvable. Wiring a resolver in collides with safety-contract items 1 (no
network egress) and 8 (no code loaded from disk at runtime). This needs a stated position
before more code is written. Also unbuilt and relevant to this audience: `UsdPhysics`
support — the package touches only `UsdGeom` and `UsdShade`, and physics is where
robotics' equivalent failures live. Note that todo #1 is a physics question answered
purely through composition, which is evidence the composition angle reaches further than
the schema coverage suggests.

## Next Step

Start with #2. It is the strongest match of the three — the asker has already narrowed it
to a USD semantics question and asked it explicitly, so the reply can be short, concrete,
and verifiable. Reproduce the shared-HDRI behaviour locally with two cloned env prims
before writing anything, and confirm whether Isaac Lab's env cloning marks them
instanceable; that fact decides the whole answer.

/home/menser/Dropbox/ai/code/usd_mcp_master
