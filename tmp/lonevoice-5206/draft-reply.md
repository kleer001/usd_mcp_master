Short answer to (2), because it decides the other two: **the DomeLights are not global as
prims — you really do have one per env — but their *illumination* is global, and namespace
parenting does not change that.**

Parenting a light under `/World/envs/env_1` sets where it *is*. It does not set what it
*lights*. What a light lights is a collection, and that collection defaults to the whole
stage.

### Your authoring worked; that's the confusing part

I rebuilt your setup in plain USD — two envs, one `DomeLight` under each, different
`inputs:texture:file` on each — and both opinions land cleanly:

```
/World/envs/env_0/Light  texture=@studio.hdr@
/World/envs/env_1/Light  texture=@sunset.hdr@
```

No contest, no override, nothing lost. So the "one overrides the other" theory is out —
neither one overrode anything.

### What actually happens

`UsdLux.LightAPI` carries a `lightLink` collection, and the schema default (USD 26.08) is
`uniform bool collection:lightLink:includeRoot = 1`. Root included means every prim on the
stage is a member. Asking each light which geometry it illuminates:

```
/World/envs/env_0/Light  ->  lights ['/World/envs/env_0/Robot', '/World/envs/env_1/Robot']
/World/envs/env_1/Light  ->  lights ['/World/envs/env_0/Robot', '/World/envs/env_1/Robot']
```

Both lights light both envs. You don't have two isolated environments, you have two
overlapping full-stage environment lights, and the renderer resolves that however it
resolves it. Add that the schema defines a `DomeLight` as "light emitted inward from a
*distant external environment*" — an environment map, not a lamp with a position — so I
would not expect translating it by the env spacing to buy you anything either, though
that part I haven't put in front of a renderer.

### (1) and (3) — what you can actually do

**To scope illumination**, author the light link explicitly — turn off `includeRoot` and
include only that env:

```python
coll = UsdLux.LightAPI(light_prim).GetLightLinkCollectionAPI()
coll.CreateIncludeRootAttr(False)
coll.CreateIncludesRel().SetTargets([Sdf.Path(f"/World/envs/env_{i}")])
```

That does what you'd expect at the USD level — I ran the same membership query afterwards:

```
/World/envs/env_0/Light  ->  lights ['/World/envs/env_0/Robot']
/World/envs/env_1/Light  ->  lights ['/World/envs/env_1/Robot']
```

Two caveats I'd rather flag than let you discover:

- I can't find `lightLink`, `light_link` or `LightLinkCollection` anywhere in the Isaac Lab
  source (GitHub code search across the repo, zero hits each — same search returns 102 for
  `DomeLightCfg`, so it is indexing fine). So there's no `LightCfg` field for this; you'd be
  authoring it yourself on the spawned prim. And **whether the RTX renderer honors light
  linking on a dome light is the part I can't test here** — worth checking before you build
  on it.
- **Light linking scopes what a light illuminates. It is a collection of geometry — there is
  nothing in it about primary rays.** So I would not expect it to change what the camera
  sees behind your scene, which means `visible_in_primary_ray=True` on two linked domes is
  unlikely to give you two backdrops. Also untested by me, but the mechanism isn't there to
  do it.

**For per-env visual diversity specifically**, the engine seems to run the other way — one
dome for the environment, per-env local lights for variation. In #4621 an Isaac Lab
collaborator answering the same general question sketched exactly that shape ("single dome
light + per-env sphere lights"), though they flagged their own answer as still under
review. And #6289 switches Cartpole from `DomeLight` to `DistantLight` as the first proof
of concept in what it calls "a wider effort to update the default lighting set-up in
IsaacLab" — its stated reasons include cross-environment shadow inconsistency (from the
auto-created distant light) and that `DistantLight`s generally produce fewer artifacts,
"with the exception of using DomeLight(s) as an environment map."

If the diversity is for training rather than for a single frame, randomizing one dome's
`texture_file` across resets gives each episode a different HDRI. That's a different thing
from N backgrounds at once — but N backgrounds at once is the thing USD's lighting model
has no mechanism for, so it may be the trade worth making.

---

*The composition half of this I worked out with
[usd_mcp](https://github.com/kleer001/usd_mcp_master), a tool I wrote (read-only by
default) for exactly this shape of question — "I authored it, so why isn't it winning".
Here it earned its keep by proving the opposite: the opinions were fine, so the bug had to
be somewhere other than composition.*
