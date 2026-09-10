# tmp/ — outreach drafts and their evidence

Drafted replies to unanswered OpenUSD questions on the `isaac-sim/IsaacLab`
discussion board, with the scripts that verified each one. Tracked rather than
ignored so they can be read from another machine.

Nothing here has been posted. Each draft is final text awaiting a decision.

## Layout

```
lonevoice-<discussion>/
  draft-reply.md   the reply, as it would be posted
  *.py             runnable scripts; each prints the output quoted in the draft
  *.usda           USD stages the scripts build, regenerated on every run
artifact/
  lone-voice-drafts.html   source of the review page published as an Artifact
  patch.py                 adds the original posts and ASCII-encodes the page
op/
  <discussion>.json        each original post as fetched from the GitHub API
```

## The three drafts

| Discussion | Subject | Verified root cause |
|---|---|---|
| 4828 | Collision on a Blender-exported USD will not persist | The `UsdFileCfg` spawn path calls `modify_collision_properties`, which returns `False` on any prim lacking `CollisionAPI` and never applies it. A Blender export declares none, so it is a silent no-op. Identical in v2.0.0, v2.2.0 and main. |
| 5206 | Per-environment HDRI backgrounds in parallel envs | `collection:lightLink:includeRoot` defaults to `1`, so every light illuminates the whole stage. Namespace parenting scopes nothing. Both per-env textures author cleanly, so no opinion is being overridden. |
| 6020 | Ray caster returns no hits | `vertical_fov_range=(0.0, 0.0)` makes every one of the 71 rays exactly horizontal, cast against a single flat surface. A mechanism that fits the symptoms, not a confirmed diagnosis — the draft says so and offers two checks. |

## Running the scripts

They need the `pxr` bindings from the project venv:

```bash
.venv/bin/python tmp/lonevoice-5206/repro.py
```

Each is self-contained and rebuilds the stages it needs, so any claim in a draft
can be checked rather than taken on trust.
