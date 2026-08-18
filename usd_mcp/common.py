"""Boundary helpers shared by the explainers.

Opening a stage, demanding a prim, and converting USD's C++ types to Python ones
are the three things every explainer does before it can say anything. They live
here so both explainer modules convert at the same boundary rather than each
growing its own.
"""

import os
from collections import OrderedDict

from pxr import Sdf, Tf, Usd

# Composing a stage dominates a tool call that reads one prim: on a 200-layer, 10,000-prim
# stage, opening costs ~66 ms and answering the question afterwards costs ~0.04 ms. A
# single question does not care. A sweep of several thousand does — six thousand of them
# is six minutes of composition and a fifth of a second of work.
#
# So a cache is worth having and is off unless asked for, on the same reasoning as the
# write path: it changes what an answer can be wrong about. A cached stage is served only
# when every layer it uses still has the mtime it had when it was composed, which costs
# under a millisecond to check against the 66 ms it saves. It cannot see a file that did
# not exist when the stage was composed and does now — a reference that was broken and is
# no longer resolves to nothing on a cache hit — which is the reason this is opt-in rather
# than the default. Holding a stage is also what keeps its layers in memory, and USD will
# not re-read a layer it already holds, so a fingerprint miss drops every cached stage
# rather than only the one that moved.
_stage_cache = None
_cache_limit = 0


def enable_stage_cache(limit=4):
    """Serve repeated opens of an unchanged stage from memory. Off until called.

    Bounded by stage count rather than by bytes: a production stage's footprint is not
    knowable in advance, and four of them is already a deliberate amount of memory.
    """
    global _stage_cache, _cache_limit
    _stage_cache = OrderedDict()
    _cache_limit = limit



def open_stage(stage_path, load_payloads=True, cached=True):
    """Open a stage, or raise `ValueError` naming what went wrong.

    `cached=False` always composes afresh. The write path passes it: an authored stage
    that fails to save holds an edit no fingerprint can see, and serving that to a reader
    would report scene description that is not on disk.

    `load_payloads=False` composes the stage without pulling payload contents in,
    matching a session that deferred them. It changes the answer: an unloaded
    payload's descendants are absent, and a prim whose type comes from inside the
    payload composes as untyped.

    Every way of failing to open a stage — missing file, wrong format, malformed
    scene description — surfaces from USD as `Tf.ErrorException`, which carries the
    parse error but not a type any caller here would think to catch. Translating it
    at this boundary is what makes the `ValueError` contract the rest of the package
    documents actually hold.
    """
    if not cached or _stage_cache is None:
        return _compose(stage_path, load_payloads)

    key = (os.path.realpath(stage_path), load_payloads)
    entry = _stage_cache.get(key)
    if entry is not None:
        if entry[1] == _fingerprint(entry[0]):
            _stage_cache.move_to_end(key)
            return entry[0]
        # USD will not re-read a layer that is still in memory, and a cached stage is
        # what keeps it there. Dropping every cached stage — not just this one, since
        # stages share layers — is what lets the recomposed stage read the new file.
        del entry
        _stage_cache.clear()

    stage = _compose(stage_path, load_payloads)
    _stage_cache[key] = (stage, _fingerprint(stage))
    _stage_cache.move_to_end(key)
    while len(_stage_cache) > _cache_limit:
        _stage_cache.popitem(last=False)
    return stage


def _compose(stage_path, load_payloads):
    load = Usd.Stage.LoadAll if load_payloads else Usd.Stage.LoadNone
    try:
        stage = Usd.Stage.Open(stage_path, load=load)
    except Tf.ErrorException as error:
        raise ValueError(f"could not open as a USD stage: {stage_path}: {error}") from error
    if not stage:
        raise ValueError(f"could not open as a USD stage: {stage_path}")
    return stage


def _fingerprint(stage):
    """The on-disk state of every file this stage composed from.

    A missing file is a changed one: it fingerprints as `None` and no longer matches what
    was recorded when the stage was composed. Anonymous layers have no file to check.
    """
    marks = []
    for layer in stage.GetUsedLayers():
        path = layer.realPath
        if not path:
            continue
        try:
            marks.append((path, os.stat(path).st_mtime_ns))
        except OSError:
            marks.append((path, None))
    return tuple(sorted(marks))


def open_layer(layer_path):
    """Open a single layer as authored, or raise `ValueError` naming what went wrong.

    `open_stage` composes; this does not. A per-layer diff asks what one file says,
    which is a different question from what the stage resolved to, and composing to
    answer it would fold in every sublayer and reference the file happens to name.
    """
    try:
        layer = Sdf.Layer.FindOrOpen(layer_path)
    except Tf.ErrorException as error:
        raise ValueError(f"could not open as a USD layer: {layer_path}: {error}") from error
    if not layer:
        raise ValueError(f"could not open as a USD layer: {layer_path}")
    return layer


def require_prim(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"no prim at {prim_path}")
    return prim


def require_attribute(prim, attribute_name):
    attr = prim.GetAttribute(attribute_name)
    if not attr:
        raise ValueError(f"{prim.GetPath()} has no attribute {attribute_name!r}")
    return attr


def prim_specs(layer):
    """Every prim spec a layer authors, in no particular order, variants included.

    Walking `nameChildren` down from the root prims misses everything inside a variant:
    a variant's contents hang off the variant set rather than off the prim, and they are
    as authored as the rest of the file. `Sdf.Layer.Traverse` reaches them.
    """
    paths = []
    layer.Traverse(Sdf.Path.absoluteRootPath, paths.append)
    for path in paths:
        spec = layer.GetPrimAtPath(path)
        if spec is not None and path != Sdf.Path.absoluteRootPath:
            yield spec


def root_layer_stack(stage):
    """The stage's layer stack, strongest first, without the session layer.

    A stage always carries an anonymous session layer that nobody authored and
    nobody can open. Reporting it as part of the layer stack invites an edit
    aimed at a layer that will not survive the session.
    """
    return stage.GetLayerStack(includeSessionLayers=False)


def plain(value):
    """USD values are C++ types; JSON needs Python ones."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Sdf.AssetPath):
        # str() of an asset path yields USD's source syntax, @like this@, and drops the
        # resolved location — the one fact worth having about a texture or a reference.
        # A null resolved_path is a broken asset path stated plainly.
        return {
            "asset_path": value.path,
            "resolved_path": value.resolvedPath or None,
        }
    if hasattr(value, "__len__") and not isinstance(value, str):
        return [plain(item) for item in value]
    return str(value)


# A result that does not fit in the caller's context window is not a smaller answer, it
# is no answer: an agent that receives 397,000 tokens of changed attributes loses the
# conversation the question was asked in. Measured on a 200-layer, 10,000-prim stage,
# `diff_stages` returned 1.59 MB and `profile_stage` 78 KB, and production robotics and
# geospatial scenes are larger again.
#
# Fifty holds every bounded result under about 25 KB. It is deliberately one number
# rather than one per field: a caller reasoning about what it did not see should not
# have to remember which list stops where.
MAX_ITEMS = 50


def bounded(field, items, limit=MAX_ITEMS):
    """`{field: items}` trimmed to `limit`, saying so when the trim bit.

    Truncation that does not announce itself reads as a complete answer, so a trimmed
    list is always accompanied by `<field>_truncated`, giving how many were reported and
    how many there were. That key is absent when nothing was dropped — its presence is
    the signal. Splat the result into the dict being built:

        return {"stage": stage_path, **bounded("layers", layers)}
    """
    if len(items) <= limit:
        return {field: items}
    return {
        field: items[:limit],
        f"{field}_truncated": {"reported": limit, "total": len(items)},
    }
