Your attempt #1 didn't fail — it never ran. **Nothing in the `UsdFileCfg` spawn path ever
applies `UsdPhysics.CollisionAPI`. It only edits colliders the asset already declares**, and
a Blender export declares none. So `collision_props=CollisionPropertiesCfg(...)` is a silent
no-op on your board.

Here is the whole chain, and it's three hops:

`spawners/from_files/from_files.py` spawns your USD and then calls:

```python
if cfg.collision_props is not None:
    schemas.modify_collision_properties(prim_path, cfg.collision_props)
```

`modify_collision_properties` — note *modify*, not *define* — opens with:

```python
collider_prim = stage.GetPrimAtPath(prim_path)
if not UsdPhysics.CollisionAPI(collider_prim):
    return False
```

and `UsdPhysics.CollisionAPI(prim)` is falsy on a prim that hasn't had the API applied. I
checked, since it's the hinge of the whole thing:

```
no API applied  -> bool(CollisionAPI(prim)) = False
after Apply     -> bool(CollisionAPI(prim)) = True
```

`define_collision_properties`, the function that *does* call `CollisionAPI.Apply()`, is not
on this path. This is the same in v2.0.0, v2.2.0 and current main, so your version doesn't
matter here.

**There is a log line for this you probably scrolled past.** `modify_collision_properties`
is wrapped in `@apply_nested`, which walks the subtree and, when nothing succeeds anywhere,
logs:

```
Could not perform 'modify_collision_properties' on any prims under: '<your path>'.
 This might be because of the following reasons:
	(1) The desired attribute does not exist on any of the prims.
	(2) The desired attribute exists on an instanced prim.
```

A warning, not an error, so the sim comes up looking fine. Grep your log for
`Could not perform` — I'd expect it there. (Note reason 2: `apply_nested` skips instanced
prims outright. If you ever mark that board instanceable, it gets skipped for a second,
unrelated reason.)

### Why the GUI collider disappears

Different mechanism, same root. A GUI edit goes to the stage's current *edit target*, which
is the run-time stage's own layer — not into `chessboard.usdc`, which is only referenced in.
I haven't driven your GUI, but I rebuilt that shape in plain USD — a run-time stage
referencing the asset — and made the edit there:

```
after the 'GUI' edit:
  authored in runtime layer: True
  authored in asset layer  : False
```

The edit genuinely wins while the session is up, which is why it works when you test it:

```
"would_win": true,
"explanation": "An opinion authored in runtime_stage.usda would win:
                no layer stronger than it authors this attribute."
```

It wins in the one layer Isaac Lab throws away and rebuilds from your `usd_path` next run.

### The fix — bake it into the asset once

```python
from pxr import Usd, UsdGeom, UsdPhysics

stage = Usd.Stage.Open("/path/to/chessboard.usdc")
for prim in stage.Traverse():
    if prim.IsA(UsdGeom.Mesh):
        UsdPhysics.CollisionAPI.Apply(prim)
        api = UsdPhysics.MeshCollisionAPI.Apply(prim)
        api.CreateApproximationAttr(UsdPhysics.Tokens.convexDecomposition)
stage.GetRootLayer().Save()
```

Run once, offline, no Isaac Sim needed. After that the prims carry the API, the gate above
passes, and your existing `collision_props=CollisionPropertiesCfg(collision_enabled=True)`
starts doing something. Verified on a stand-in asset:

```
before:  /ChessBoard/Board_mesh   CollisionAPI=False  MeshCollisionAPI=False
after:   /ChessBoard/Board_mesh   CollisionAPI=True   MeshCollisionAPI=True  approximation=convexDecomposition
```

Apply it to the **mesh** prims, not the top-level Xform — the collider has to sit on the
geometry, and `apply_nested` walking down from the spawn path to the meshes is what then
finds it.

### Your attempt #2

There is no `mesh_approximation` parameter — the approximation is chosen by *which config
class* you use, not by an argument. `ConvexDecompositionPropertiesCfg`,
`ConvexHullPropertiesCfg`, `TriangleMeshPropertiesCfg`, `SDFMeshPropertiesCfg` and friends
each carry their own `mesh_approximation_name`. On current main these have moved to
`isaaclab_physx.sim.schemas` with `Physx*` names and the old names kept as deprecation
aliases, so check what your version actually exports before copying names from anyone's
snippet — this is the part of the API that has moved most.

### Your attempt #3 — the ~700 vs ~2 scale

Can't diagnose that from here, but the first thing I'd check is stage units rather than
anything about your geometry:

```python
from pxr import Usd, UsdGeom
for f in ("blender_export.usdc", "isaac_export.usdc"):
    s = Usd.Stage.Open(f)
    print(f, UsdGeom.GetStageMetersPerUnit(s), UsdGeom.GetStageUpAxis(s))
```

If those differ between the two files, the number is a unit conversion and not a modelling
problem. Worth ruling out before chasing it further.

---

*The layer half of this I worked out with
[usd_mcp](https://github.com/kleer001/usd_mcp_master), a tool I wrote (read-only by default)
for "I authored it, so why didn't it stick" — the `would_win` output above is its
`edit-target` command. It has no physics support, so the bake script is plain `pxr`.*
