"""The other half of #4828: why the GUI-added collider vanishes on reload.

Mimics the Isaac Lab shape - a run-time stage that references the asset on disk.
An edit made in the run-time layer wins for the session and is not in the asset.
"""
import os
from pxr import Usd, UsdGeom, UsdPhysics, Sdf

RUNTIME = "tmp/lonevoice-4828/runtime_stage.usda"
if os.path.exists(RUNTIME):
    os.remove(RUNTIME)

stage = Usd.Stage.CreateNew(RUNTIME)
world = UsdGeom.Xform.Define(stage, "/World")
board = stage.DefinePrim("/World/ChessBoard")
board.GetReferences().AddReference("./chessboard.usda")
stage.GetRootLayer().Save()

mesh_path = "/World/ChessBoard/Board_mesh"
print("collisionEnabled on the referenced mesh, before any GUI edit:")
p = stage.GetPrimAtPath(mesh_path)
print("  authored in runtime layer:",
      bool(stage.GetRootLayer().GetAttributeAtPath(mesh_path + ".physics:collisionEnabled")))

# what the GUI does: author into the run-time stage's own layer
with Usd.EditContext(stage, stage.GetRootLayer()):
    UsdPhysics.CollisionAPI.Apply(p).CreateCollisionEnabledAttr(True)

print("\nafter the 'GUI' edit:")
print("  authored in runtime layer:",
      bool(stage.GetRootLayer().GetAttributeAtPath(mesh_path + ".physics:collisionEnabled")))
asset = Sdf.Layer.FindOrOpen("tmp/lonevoice-4828/chessboard.usda")
print("  authored in asset layer  :",
      bool(asset.GetAttributeAtPath("/ChessBoard/Board_mesh.physics:collisionEnabled")))
stage.GetRootLayer().Save()
print("\n  -> the opinion lives only in the layer Isaac Lab rebuilds each run.")
