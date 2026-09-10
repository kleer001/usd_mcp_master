"""Does light linking actually scope a DomeLight to one env subtree?"""
import os
from pxr import Usd, UsdLux, UsdGeom, Sdf, Gf

PATH = "tmp/lonevoice-5206/linked_envs.usda"
if os.path.exists(PATH):
    os.remove(PATH)
stage = Usd.Stage.CreateNew(PATH)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.Xform.Define(stage, "/World")
UsdGeom.Scope.Define(stage, "/World/envs")

for i, tex in enumerate(["studio.hdr", "sunset.hdr"]):
    env = UsdGeom.Xform.Define(stage, f"/World/envs/env_{i}")
    env.AddTranslateOp().Set(Gf.Vec3d(i * 5.0, 0, 0))
    UsdGeom.Cube.Define(stage, f"/World/envs/env_{i}/Robot")
    light = UsdLux.DomeLight.Define(stage, f"/World/envs/env_{i}/Light")
    light.CreateTextureFileAttr(Sdf.AssetPath(tex))
    # the fix: stop including the whole stage, include only this env
    coll = UsdLux.LightAPI(light.GetPrim()).GetLightLinkCollectionAPI()
    coll.CreateIncludeRootAttr(False)
    coll.CreateIncludesRel().SetTargets([Sdf.Path(f"/World/envs/env_{i}")])

stage.GetRootLayer().Save()

for prim in stage.Traverse():
    if not prim.IsA(UsdLux.DomeLight):
        continue
    q = Usd.CollectionAPI(prim, "lightLink").ComputeMembershipQuery()
    lit = [str(p.GetPath()) for p in stage.Traverse()
           if q.IsPathIncluded(p.GetPath()) and p.IsA(UsdGeom.Gprim)]
    print(f"{prim.GetPath()}  ->  lights {lit}")
