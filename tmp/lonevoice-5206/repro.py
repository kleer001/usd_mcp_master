"""Reproduce IsaacLab discussion #5206: per-env DomeLights in parallel envs.

Question: does parenting a DomeLight under /World/envs/env_N confine its
illumination to that env's subtree?
"""
from pxr import Usd, UsdLux, UsdGeom, Sdf, Gf

PATH = "tmp/lonevoice-5206/parallel_envs.usda"

import os
if os.path.exists(PATH):
    os.remove(PATH)
stage = Usd.Stage.CreateNew(PATH)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

UsdGeom.Xform.Define(stage, "/World")
UsdGeom.Scope.Define(stage, "/World/envs")

for i, tex in enumerate(["studio.hdr", "sunset.hdr"]):
    env = UsdGeom.Xform.Define(stage, f"/World/envs/env_{i}")
    env.AddTranslateOp().Set(Gf.Vec3d(i * 5.0, 0, 0))
    # a bit of geometry so each env has something to light
    UsdGeom.Cube.Define(stage, f"/World/envs/env_{i}/Robot")
    light = UsdLux.DomeLight.Define(stage, f"/World/envs/env_{i}/Light")
    light.CreateTextureFileAttr(Sdf.AssetPath(tex))

stage.GetRootLayer().Save()

print("=" * 70)
print("1. Did the per-env authoring land? (are there two distinct lights?)")
print("=" * 70)
for prim in stage.Traverse():
    if prim.IsA(UsdLux.DomeLight):
        dl = UsdLux.DomeLight(prim)
        print(f"  {prim.GetPath()}  texture={dl.GetTextureFileAttr().Get()}")

print()
print("=" * 70)
print("2. What does each light actually illuminate? (lightLink collection)")
print("=" * 70)
for prim in stage.Traverse():
    if not prim.IsA(UsdLux.DomeLight):
        continue
    api = UsdLux.LightAPI(prim)
    coll = api.GetLightLinkCollectionAPI()
    inc_root = coll.GetIncludeRootAttr()
    print(f"  {prim.GetPath()}")
    print(f"    includeRoot authored : {inc_root.HasAuthoredValue()}")
    print(f"    includeRoot resolved : {inc_root.Get()}")
    print(f"    includes rel targets : {coll.GetIncludesRel().GetTargets()}")
    q = Usd.CollectionAPI(prim, "lightLink").ComputeMembershipQuery()
    lit = [str(p.GetPath()) for p in stage.Traverse()
           if q.IsPathIncluded(p.GetPath()) and p.IsA(UsdGeom.Gprim)]
    print(f"    gprims it lights     : {lit}")

print()
print("=" * 70)
print("3. Stage-wide light list")
print("=" * 70)
lights = UsdLux.LightListAPI(stage.GetPrimAtPath("/World")).ComputeLightList(
    UsdLux.LightListAPI.ComputeModeIgnoreCache)
for lp in lights:
    print(f"  {lp}")
