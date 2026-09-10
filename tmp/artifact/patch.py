# -*- coding: utf-8 -*-
import html, re, io

P = "tmp/artifact/lone-voice-drafts.html"
s = io.open(P, encoding="utf-8").read()

# ---------------- 1. CSS for the original-post block ----------------
css = u"""
  /* ---------- original post ---------- */
  .op{
    padding:22px 26px 20px;border-bottom:1px solid var(--rule-soft);
    background:var(--surface-2);
    border-left:3px solid var(--rule);
  }
  .op-head{
    display:flex;align-items:baseline;justify-content:space-between;
    gap:14px;flex-wrap:wrap;margin-bottom:14px
  }
  .op-k{
    font-family:"IBM Plex Mono",monospace;font-size:10px;font-weight:600;
    letter-spacing:.13em;text-transform:uppercase;color:var(--ink-3);margin:0
  }
  .op-k b{color:var(--ink-2);font-weight:600}
  .skip{
    font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--accent-ink);
    text-decoration:none;border-bottom:1px solid var(--rule)
  }
  .skip:hover{border-bottom-color:var(--accent)}
  .op-body{max-width:68ch;font-size:14.5px;color:var(--ink-2)}
  .op-body p{margin:0 0 12px}
  .op-body strong{color:var(--ink);font-weight:600}
  .op-body ul,.op-body ol{margin:0 0 12px;padding-left:20px;display:flex;flex-direction:column;gap:6px}
  .op-body li{line-height:1.55}
  .op-body ol li::marker{font-family:"IBM Plex Mono",monospace;font-size:12.5px;color:var(--ink-3);font-weight:600}
  .op-body code{background:var(--rule-soft);color:var(--ink);font-size:.85em}
  .op-body pre{
    background:var(--surface);color:var(--ink-2);
    border:1px solid var(--rule);border-radius:2px;
    font-size:12.2px;padding:12px 14px;margin:0 0 12px
  }
  .op-body pre code{background:none;color:inherit}
  .op-body .att{
    font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--ink-3);
    display:flex;flex-direction:column;gap:5px;margin:0 0 12px
  }
  .op-body .att a{color:var(--accent-ink)}
"""
s = s.replace(u"  /* ---------- verdict ---------- */", css + u"\n  /* ---------- verdict ---------- */")

# ---------------- 2. the three original posts ----------------
OP = {}

OP["5206"] = (u"nitkizs", u"""
<p>Hi,<br>I am working with Isaac Lab using parallel environments, where environments are
cloned under paths like:</p>
<ul><li><code>/World/envs/env_0</code></li><li><code>/World/envs/env_1</code></li></ul>
<p>I want each environment to use a different HDRI background.</p>
<p>I tried creating one <code>DomeLight</code> per environment using
<code>DomeLightCfg(texture_file=...)</code>, with each dome light placed under its
corresponding environment namespace. However, both environments still appear to share the
same HDRI, or one HDRI overrides the other.</p>
<ol>
  <li>Is it possible to assign different HDRIs per environment within a single Isaac Lab
      simulation?</li>
  <li>Are <code>DomeLight</code>s effectively global in Omniverse/USD, even if authored
      under different env paths?</li>
  <li>What is the recommended way to achieve per-environment visual diversity in parallel
      environments?</li>
</ol>
<p>So far, I have tried:</p>
<ul>
  <li>creating a separate <code>DomeLight</code> under each env path</li>
  <li>setting <code>visible_in_primary_ray=True</code></li>
</ul>
<p>But the results are not isolated per environment.</p>
<p><strong>Environment:</strong></p>
<ul><li>Isaac Lab: 0.54.3</li><li>Isaac Sim: 5.1</li><li>GPU: RTX 4070</li></ul>
""")

OP["4828"] = (u"rayrsys", u"""
<p>Hi everyone,</p>
<p>I'm working on a chess manipulation environment in Isaac Lab where a G1 robot picks up and
places chess pieces on a board. The chess board and pieces are exported from Blender as USD
files.</p>
<p><strong>The problem:</strong> My chess board USD has no collision &mdash; the robot's hands
pass right through it. I can manually add a collision mesh in Isaac Sim (right-click &rarr; Add
&rarr; Physics &rarr; Colliders), and it works perfectly. But the collision doesn't persist
&mdash; every time I reload the scene, I have to add it again.</p>
<p><strong>What I've tried:</strong></p>
<p>1. Adding rigid/collision props in the Isaac Lab spawn config:</p>
<pre><code>chess_board = AssetBaseCfg(
    prim_path="/World/envs/env_.*/ChessBoard",
    spawn=UsdFileCfg(
        usd_path="/path/to/chessboard.usdc",
        scale=(0.3, 0.3, 0.3),
        rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
        collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=True),
    ),
)</code></pre>
<p>Result: No effect &mdash; the robot still passes through the board.</p>
<p>2. Adding <code>mesh_collision_props</code> with convex decomposition:</p>
<pre><code>mesh_collision_props=sim_utils.MeshCollisionPropertiesCfg(mesh_approximation="convexDecomposition")</code></pre>
<p>Result: <code>MeshCollisionPropertiesCfg</code> doesn't accept
<code>mesh_approximation</code> parameter.</p>
<p>3. Exporting from Isaac Sim after manually adding collider (Export Selected): The exported
USD file ends up at a completely different scale (~700 units vs the original ~2 units), so it
doesn't load correctly back into the scene.</p>
<p>4. Adding physics in Blender before export (Rigid Body &rarr; Passive &rarr; Collision Shape
&rarr; Mesh): Haven't confirmed if this translates to proper
<code>UsdPhysics.CollisionAPI</code> in the exported USD.</p>
<p><strong>My setup:</strong></p>
<ul>
  <li>Isaac Lab (from IsaacLab repo)</li>
  <li>Blender 4.x exporting to .usdc with "Convert to USD Preview Surface" enabled</li>
  <li>Chess board is ~2m across in Blender, scaled to 0.3 in Isaac Lab</li>
  <li>Board should be kinematic (doesn't move, but things collide with it)</li>
</ul>
<p><strong>What I need:</strong> A reliable way to either:</p>
<ul>
  <li>Export from Blender with collision baked into the USD</li>
  <li>Or programmatically add collision (with proper mesh approximation) that persists in the
      USD file</li>
  <li>Or configure Isaac Lab's spawn config to properly generate collision from the visual
      mesh</li>
</ul>
<p>Has anyone successfully exported Blender models with working collision in Isaac Lab? What's
the recommended workflow?</p>
<p>Thanks!</p>
""")

OP["6020"] = (u"ValdezNewton", u"""
<p>Hi everyone! I'm quite new to NVIDIA Isaac Lab. I've converted my robot from URDF to USD and
I'm able to move all joints of the robot successfully. However, the Ray Caster doesn't seem to
work on my robot. To debugg the issue, I tried using the <code>raycaster_sensor.py</code>
script from the Isaac Lab ray caster docs on my lunar environment. The ray caster sensors work
successfully as shown in Image 1. However, when I try to use ray caster on my robot, the red
points (representing either point cloud or LiDAR rays) aren't appearing as they do on the
<code>anymal</code> robot, as shown in Image 2.</p>
<p>When I ran my code that uses Ray Caster for my robot, I received errors as shown below:</p>
<pre><code>  File ".../isaaclab/sensors/ray_caster/ray_caster.py", line 329, in _debug_vis_callback
    self.ray_visualizer.visualize(viz_points)
  File ".../isaaclab/markers/visualization_markers.py", line 334, in visualize
    raise ValueError("Number of markers cannot be zero! Hint: The function was called with no inputs?")
ValueError: Number of markers cannot be zero! Hint: The function was called with no inputs?</code></pre>
<p>My initial thought was because I didn't create a dedicated location for the Ray Caster.
Therefore, I created a <code>lidar_link</code> cylinder shape and use a <code>Fixed Joint</code>
to attach it to my chassis, and place the ray caster on that cylinder, but it failed, and
prompted the same errors as shown above.</p>
<p>The part of the code that I've written that uses Ray Caster is shown below:</p>
<pre><code># 360-Degree LiDAR for Obstacle Avoidance
LUNARBOT_LIDAR_CFG = RayCasterCfg(
    prim_path="{ENV_REGEX_NS}/Robot",
    offset=RayCasterCfg.OffsetCfg(pos=(0.0, 0.5, 0.35)),
    ray_alignment="yaw",
    pattern_cfg=patterns.LidarPatternCfg(
        channels=1,
        vertical_fov_range=(0.0, 0.0),
        horizontal_fov_range=(-180.0, 180.0),
        horizontal_res=5.0,
    ),
    max_distance=15.0,
    debug_vis=True, # Will now generate exactly 72 markers per robot!
    mesh_prim_paths=["/World/Terrain"],
)</code></pre>
<p><strong>Information on the environment:</strong> The environment consists of multiple lunar
rocks and four walls that borders the vicinity of the ground plane. The lunar rocks and the four
walls are merged together as a single mesh. The merged mesh contains Collision API but no rigid
body property. The lunar rocks have a height higher than 5 meters.</p>
<p><strong>Information on my robot (LunarBot):</strong> My LunarBot was converted from URDF to
USD. All joints are working, and I can move it just like a regular robot. It can also collide
with the lunar rocks in the environment. However, I'm unable to use Ray Caster on it.</p>
<p class="att">
  <span>Attached to the original post:</span>
  <span>Image 1 &mdash; anymal raycaster working &middot; Image 2 &mdash; LunarBot raycaster
  failure &middot; Image 3 &mdash; LunarBot</span>
  <span>lunarbot_cfg.py &middot; lunarbot_raycaster.py</span>
</p>
<p>Can someone kindly help me in this matter? I hope to learn more from everyone!</p>
""")

# ---------------- 3. insert OP blocks + asker into meta ----------------
for did, (who, bodyhtml) in OP.items():
    block = (
        u'    <section class="op" id="op-' + did + u'">\n'
        u'      <div class="op-head">\n'
        u'        <p class="op-k">The question, as asked · <b>@' + who + u'</b></p>\n'
        u'        <a class="skip" href="#reply-' + did + u'">skip to my reply ↓</a>\n'
        u'      </div>\n'
        u'      <div class="op-body">' + bodyhtml + u'</div>\n'
        u'    </section>\n'
    )
    # insert before that panel's rootcause
    marker = u'<section class="pane" id="panel-' + did + u'"'
    i = s.index(marker)
    j = s.index(u'<div class="rootcause">', i)
    j = s.rindex(u'\n', i, j) + 1
    s = s[:j] + block + s[j:]

    # anchor on the reply body
    k = s.index(u'<div class="body">', s.index(marker))
    s = s[:k] + u'<div class="body" id="reply-' + did + u'">' + s[k + len(u'<div class="body">'):]

    # asker handle into the meta row
    m = s.index(u'<div class="meta-row">', s.index(marker))
    e = s.index(u'>', m) + 1
    s = s[:e] + u'\n        <span>asked by @' + who + u'</span>' + s[e:]

# ---------------- 4. every non-ASCII char -> HTML entity ----------------
NAMED = {
    u'—': u'&mdash;', u'–': u'&ndash;', u'−': u'&minus;',
    u'·': u'&middot;', u'°': u'&deg;', u'…': u'&hellip;',
    u'→': u'&rarr;', u'↓': u'&darr;', u'↑': u'&uarr;',
    u'’': u'&rsquo;', u'‘': u'&lsquo;',
    u'“': u'&ldquo;', u'”': u'&rdquo;', u' ': u'&nbsp;',
}
out = []
converted = {}
for ch in s:
    if ord(ch) < 128:
        out.append(ch)
    else:
        ent = NAMED.get(ch) or (u'&#%d;' % ord(ch))
        converted[ch] = converted.get(ch, 0) + 1
        out.append(ent)
s = u"".join(out)

io.open(P, "w", encoding="ascii").write(s)
print("original posts inserted: %d" % len(OP))
print("non-ASCII chars converted to entities:")
for ch, n in sorted(converted.items(), key=lambda kv: -kv[1]):
    print("   U+%04X %-10r x%d -> %s" % (ord(ch), ch, n, NAMED.get(ch, '&#%d;' % ord(ch))))
print("file is now pure ASCII:", all(ord(c) < 128 for c in s))
