"""IsaacLab #4828: bake collision into a Blender-exported USD so it persists.

Simulates the Blender export (a mesh, no physics schemas), shows why Isaac Lab's
spawn-time collision_props is a no-op on it, then bakes the collider in.
"""
import os
from pxr import Usd, UsdGeom, UsdPhysics, Sdf, Gf

ASSET = "tmp/lonevoice-4828/chessboard.usda"
if os.path.exists(ASSET):
    os.remove(ASSET)

# --- what Blender gives you -------------------------------------------------
stage = Usd.Stage.CreateNew(ASSET)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
board = UsdGeom.Xform.Define(stage, "/ChessBoard")
stage.SetDefaultPrim(board.GetPrim())
mesh = UsdGeom.Mesh.Define(stage, "/ChessBoard/Board_mesh")
mesh.CreatePointsAttr([Gf.Vec3f(-1, -1, 0), Gf.Vec3f(1, -1, 0),
                       Gf.Vec3f(1, 1, 0), Gf.Vec3f(-1, 1, 0)])
mesh.CreateFaceVertexCountsAttr([4])
mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
stage.GetRootLayer().Save()

def survey(tag):
    s = Usd.Stage.Open(ASSET)
    print(f"\n--- {tag}")
    for p in s.Traverse():
        has_c = p.HasAPI(UsdPhysics.CollisionAPI)
        has_m = p.HasAPI(UsdPhysics.MeshCollisionAPI)
        approx = None
        if has_m:
            approx = UsdPhysics.MeshCollisionAPI(p).GetApproximationAttr().Get()
        print(f"  {str(p.GetPath()):32} CollisionAPI={has_c}  MeshCollisionAPI={has_m}"
              + (f"  approximation={approx}" if approx else ""))

survey("as exported from Blender")

# Isaac Lab's modify_collision_properties gate, verbatim in spirit:
#   if not UsdPhysics.CollisionAPI(prim): return False
s = Usd.Stage.Open(ASSET)
print("\n  Isaac Lab's gate on each prim -> "
      + str({str(p.GetPath()): bool(UsdPhysics.CollisionAPI(p)) for p in s.Traverse()}))
print("  ...every prim returns False, so collision_props edits nothing.")

# --- the fix: author the schema into the asset layer -------------------------
s = Usd.Stage.Open(ASSET)
for p in s.Traverse():
    if p.IsA(UsdGeom.Mesh):
        UsdPhysics.CollisionAPI.Apply(p)
        m = UsdPhysics.MeshCollisionAPI.Apply(p)
        m.CreateApproximationAttr(UsdPhysics.Tokens.convexDecomposition)
s.GetRootLayer().Save()

survey("after baking collision into the asset layer")
s = Usd.Stage.Open(ASSET)
print("\n  Isaac Lab's gate now       -> "
      + str({str(p.GetPath()): bool(UsdPhysics.CollisionAPI(p)) for p in s.Traverse()}))
