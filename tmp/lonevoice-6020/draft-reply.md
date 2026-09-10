That error is not the ray caster failing to initialize. It initialized fine. Look at what
raises it (`ray_caster.py`, v2.3.0):

```python
def _debug_vis_callback(self, event):
    # remove possible inf values
    viz_points = self._data.ray_hits_w.reshape(-1, 3)
    viz_points = viz_points[~torch.any(torch.isinf(viz_points), dim=1)]
    self.ray_visualizer.visualize(viz_points)
```

A ray that hits nothing comes back `inf` and gets filtered out. Zero markers means **every
ray missed**. The sensor is running and aimed — it's just hitting nothing, which is a much
smaller problem than "the ray caster doesn't work on my robot."

### Compare your config against the demo you copied

The demo script you linked configures it like this:

```python
ray_caster = RayCasterCfg(
    prim_path="{ENV_REGEX_NS}/Robot/base/lidar_cage",
    offset=RayCasterCfg.OffsetCfg(pos=(0, 0, 0.5)),
    mesh_prim_paths=["/World/Ground"],
    ray_alignment="yaw",
    pattern_cfg=patterns.LidarPatternCfg(
        channels=100, vertical_fov_range=[-90, 90], horizontal_fov_range=[-90, 90], horizontal_res=1.0
    ),
)
```

Same sensor, same pattern class as yours. Two things differ, and the second is the one I'd
bet on:

1. `prim_path` points at `Robot/base/lidar_cage` — a specific body — not at the articulation
   root. You already tried adding a `lidar_link` and pointing at it, so you've effectively
   tested this one.
2. `vertical_fov_range=[-90, 90]` across `channels=100`. Yours is `(0.0, 0.0)` across
   `channels=1`. **That is the variable you never moved**, through both of your attempts.

### Why `(0.0, 0.0)` can't hit a floor

`lidar_pattern` computes `z = sin(vertical_angle)`. At a vertical range of zero, every ray
direction has `z = 0` exactly. I ran the pattern math from `patterns.py`:

```
num_horizontal_angles = ceil(360/5) = 72
360-degree wrap detected -> drop last -> 71 rays actually cast
z-component of every ray direction: min=0.0  max=0.0
=> every ray is exactly horizontal.
```

(Incidentally it's 71 rays, not the 72 your comment expects — the pattern drops the last
sample on a full 360° sweep so it doesn't double up.)

Now what you're casting *at*. `_initialize_warp_meshes` doesn't use all the geometry under
`mesh_prim_paths` — it picks exactly one thing, and checks for a `Plane` first:

```python
mesh_prim = sim_utils.get_first_matching_child_prim(
    mesh_prim_path, lambda prim: prim.GetTypeName() == "Plane"
)
if mesh_prim is None:
    mesh_prim = sim_utils.get_first_matching_child_prim(
        mesh_prim_path, lambda prim: prim.GetTypeName() == "Mesh"
    )
```

If anything under `/World/Terrain` is a `Plane`, it builds an infinite flat plane at height 0
and never reads your rocks at all. Otherwise it takes the *first* Mesh in traversal order,
singular. You mentioned a ground plane alongside the merged rock-and-wall mesh, so there's a
fair chance it grabbed the flat one and stopped.

Perfectly horizontal rays, 0.35 m up, against a flat horizontal surface: parallel lines,
nothing intersects, everything `inf`, zero markers. The demo doesn't hit this because its
rays sweep down to −90°.

### Two checks, both quick

**1. Find out which mesh it actually took.** Initialization logs it:

```
Read mesh prim: <path> with N vertices and M faces.
```

That names the geometry you're really casting against. If it names your ground plane — or if
you see `Created infinite plane mesh prim` instead — that's your answer.

**2. Tilt the rays.** This is the decisive test:

```python
pattern_cfg=patterns.LidarPatternCfg(
    channels=4,
    vertical_fov_range=(-15.0, 5.0),   # was (0.0, 0.0)
    horizontal_fov_range=(-180.0, 180.0),
    horizontal_res=5.0,
),
```

If markers appear immediately, that's it, and the real fix is to point `mesh_prim_paths` at
the merged rock mesh rather than at a parent that contains the ground plane first. Note
`_initialize_warp_meshes` raises `NotImplementedError` on more than one entry there, so you
get exactly one and it needs to be the right one.

I can't see your stage, so this is the mechanism that fits your symptoms rather than a
confirmed diagnosis — but either check above should settle it in a couple of minutes.
