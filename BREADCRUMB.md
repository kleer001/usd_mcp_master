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

- [ ] #5 **START HERE. Open the drafts page and read it.** All three replies below are
      written, verified and audited; the only thing left on them is your verdict, and the
      page is where you give it.
      https://claude.ai/code/artifact/81081d51-78fb-40c9-88b5-fe65767744bb
      Each panel carries the original question as asked, the one-line root cause, the full
      draft, and a Post / Revise / Hold control. Verdicts persist in the artifact's `db`
      under `verdicts/<discussion>` — read them back with the Artifact tool's `read_db`
      (`db_op: "get"`, `collection: "verdicts"`, `doc_id: "5206"` and so on) rather than
      asking again. A verdict of `null` means unread, not rejected.

### Sequential

- [ ] #1 (needs: #5) Post the #4828 reply — "How to save collision mesh to a
      Blender-exported USD so it persists". Draft is final at
      `tmp/lonevoice-4828/draft-reply.md`. Verified root cause: the `UsdFileCfg` spawn path
      calls `modify_collision_properties`, which returns `False` on any prim lacking
      `CollisionAPI` and never applies it, so it is a silent no-op on a Blender export.
      Identical in v2.0.0, v2.2.0 and main. Post only what the verdict approves.
      https://github.com/isaac-sim/IsaacLab/discussions/4828
- [ ] #2 (needs: #5) Post the #5206 reply — "How to use different HDRI backgrounds per
      environment in parallel environments?". Draft is final at
      `tmp/lonevoice-5206/draft-reply.md`. Verified root cause:
      `collection:lightLink:includeRoot` defaults to `1`, so every light lights the whole
      stage and namespace parenting scopes nothing. The earlier instancing theory was
      wrong — both per-env textures author cleanly.
      https://github.com/isaac-sim/IsaacLab/discussions/5206
- [ ] #3 (needs: #5) Post the #6020 reply — "Ray Caster isn't working for my Robot".
      Draft is final at `tmp/lonevoice-6020/draft-reply.md`, and it is the weakest of the
      three by design: a mechanism plus two decisive checks, not a confirmed diagnosis.
      `vertical_fov_range=(0.0, 0.0)` makes all 71 rays exactly horizontal against a single
      flat surface. Instancing is **not** the cause; that theory is dropped.
      https://github.com/isaac-sim/IsaacLab/discussions/6020
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

**Three replies are drafted, verified and audited, waiting only on approval to post.**
Each is in `tmp/lonevoice-<discussion>/draft-reply.md`, with its runnable evidence beside
it. All three ran through `copy:honest`; that audit caught a 404 repo URL (the real one is
`kleer001/usd_mcp_master`, not `kleer001/usd_mcp`) and a wrong claim about the anymal demo.

- **#5206 (HDRI)** — root cause verified: `collection:lightLink:includeRoot` defaults to
  `1`, so every light lights the whole stage and namespace parenting scopes nothing. Both
  per-env textures author cleanly, so the "override" theory is out. `repro.py` shows each
  dome lighting both envs; `fix.py` shows light linking scoping them correctly. Unverified
  and flagged as such in the draft: whether RTX honors light linking on a dome.
- **#4828 (collision)** — root cause verified: the `UsdFileCfg` spawn path calls
  `schemas.modify_collision_properties`, which returns `False` on any prim lacking
  `CollisionAPI` and never applies it. Blender exports declare none, so it is a silent
  no-op that only logs `Could not perform ... on any prims under`. Identical in v2.0.0,
  v2.2.0 and main, so version-independent. `bake_collision.py` proves the fix.
- **#6020 (raycaster)** — instancing is **not** the cause; that theory is dropped. The
  verified mechanism instead: `vertical_fov_range=(0.0, 0.0)` makes `z = sin(0) = 0` for
  all 71 rays, so they are exactly horizontal, while `_initialize_warp_meshes` casts
  against a single flat surface (`Plane` branch, else first Mesh found). The working demo
  differs only in `vertical_fov_range=[-90, 90]` and a body-level `prim_path`. Posted as a
  mechanism plus two decisive checks, explicitly not as a confirmed diagnosis.

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
its absence is the signal. **Result: the asker (`kerenR1`) marked it the accepted answer
14 hours later, 2026-08-19T08:02Z.** No comment text and no reaction, so the acceptance is
the whole signal — but the method works and the channel is live.
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

Open the drafts page (#5) and put it in front of the user before doing anything else — that
is the whole reason this breadcrumb exists in its current state:
https://claude.ai/code/artifact/81081d51-78fb-40c9-88b5-fe65767744bb

Check the stored verdicts first with the Artifact tool's `read_db`. If a verdict is already
recorded for a discussion, act on it instead of re-asking. If none are recorded, surface the
page and wait — do not post anything to GitHub without approval on that specific text.

/home/menser/Dropbox/ai/code/usd_mcp_master
