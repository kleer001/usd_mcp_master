"""Boundary helpers shared by the explainers.

Opening a stage, demanding a prim, and converting USD's C++ types to Python ones
are the three things every explainer does before it can say anything. They live
here so both explainer modules convert at the same boundary rather than each
growing its own.
"""

import json
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
        #
        # `del entry` is not tidying and not a no-op: `entry` still holds the stale stage,
        # and `_compose` runs below while this frame is live. Clearing the dict alone
        # leaves that last reference holding the old layers in USD's registry, and the
        # recomposed stage reads the scene description that was already in memory —
        # silently, with the pre-edit value and no error.
        # `test_a_recomposed_stage_reads_the_edited_file` fails if this line goes.
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


def _is_array(value):
    """Whether `plain` expands this value element by element.

    Shared with `bounded_plain` so the two cannot disagree about what an array is. A
    disagreement either way is silent: converting whole a value the budget meant to
    sample, or sampling one that was never a sequence.
    """
    return hasattr(value, "__len__") and not isinstance(value, (str, dict, Sdf.AssetPath))


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
    if isinstance(value, dict):
        # Iterating a dict yields its keys, so the array branch below would report
        # `customData = {"author": "kim"}` as `["author"]` — the values silently gone.
        return {str(key): plain(item) for key, item in value.items()}
    if _is_array(value):
        return [plain(item) for item in value]
    return str(value)


# A result that does not fit in the caller's context window is not a smaller answer, it is
# no answer. Both budgets below were set from a sweep of production USD — the
# `usd-wg/assets` collection and NVIDIA's Isaac Sim asset library — measured with the
# bounds switched off, so they cap what actually happens rather than what might.
#
# The two answers were nothing alike.
#
#   result lists   never large. Unbounded, `profile_stage` peaked at 9 KB across every
#                  stage in both collections and `check_portability` at 65 KB. No list
#                  needs trimming; the budget is a backstop for the stage nobody has
#                  profiled yet, set four times above anything measured. Only a diff of
#                  two broadly different stages can reach it.
#   array values   genuinely enormous. One `points` attribute on `UsdCookie` — an
#                  ordinary sample asset — serialises to 15.1 MB, about four million
#                  tokens, from a single tool call. The largest array found held 713,718
#                  elements, some 22 MB on its own.
#
# Both are byte budgets, because entry costs differ by nearly sevenfold: a layer-stack
# identifier runs about 135 bytes and a material report about 913. One entry count lands
# those at wildly different prices; a budget lands them at the same one, and needs no
# per-field table to keep it there.
#
# Values get the tighter budget because in a composition answer the array is the subject,
# not the answer: enough of it to see what it is, not all of it. At 25 KB an ordinary mesh
# attribute passes whole — the 90th-percentile array in that sweep was 750 elements, about
# 17 KB — and only the outliers are sampled. Bulk geometry is what `usdcat` is for.
#
# Both front doors bound by default, because a shell is not reliably a pipe: the same
# stdout reaches a terminal and an agent's shell tool, and an agent driving `usd-explain`
# spends the output against a context window exactly as an MCP client does. `--full` turns
# the budgets off for the caller that genuinely wants every element — a script writing to
# a file, which asks once and deliberately.
MAX_FIELD_BYTES = 256_000
MAX_VALUE_BYTES = 25_000


def unbound_results():
    """Report every list and value whole, however large. Bounded until called.

    For a caller whose output goes to a pipe or a file rather than into a context window.
    `usd-explain --full` calls this at startup; nothing else does, because a result that
    overruns the window it lands in is not a smaller answer, it is no answer.
    """
    global MAX_FIELD_BYTES, MAX_VALUE_BYTES
    MAX_FIELD_BYTES = MAX_VALUE_BYTES = None


def _fit(items, budget):
    """How many leading entries fit the budget, or all of them when there is none.

    Costs one `json.dumps` per entry reported, not per entry held: the walk stops at the
    budget, so a hundred-thousand-entry array is priced a few hundred entries deep and no
    further. A field that answered with nothing would say less than one that answered with
    too much, hence the floor of one.
    """
    if budget is None:
        return len(items)
    kept = spent = 0
    for item in items:
        spent += len(json.dumps(item, default=str)) + 1
        if spent > budget and kept:
            break
        kept += 1
    return kept


def bounded(field, items, budget=None):
    """`{field: items}` trimmed to `budget` bytes, saying so when the trim bit.

    Truncation that does not announce itself reads as a complete answer, so a trimmed
    list is always accompanied by `<field>_truncated`, giving how many were reported and
    how many there were. That key is absent when nothing was dropped — its presence is
    the signal. Splat the result into the dict being built:

        return {"stage": stage_path, **bounded("layers", layers)}
    """
    kept = _fit(items, MAX_FIELD_BYTES if budget is None else budget)
    if kept >= len(items):
        return {field: items}
    return {
        field: items[:kept],
        f"{field}_truncated": {"reported": kept, "total": len(items)},
    }


def bounded_value(value, budget=None):
    """An authored value, trimmed when it is a large array, saying so when it is.

    An array is the one value type with no upper size, and the ceiling is not theoretical:
    a single `points` attribute in the USD working group's own sample collection is 15.1 MB
    of JSON. A trimmed array becomes a dict rather than a shorter list, because a shorter
    list reads as the whole value and nothing in it says otherwise.

    `plain()` itself stays exact. `diff_stages` compares its output element by element,
    and a comparison against a truncated array would report two different meshes as
    identical — a confident wrong answer, which costs more than a large one.
    """
    if not isinstance(value, list):
        return value
    kept = _fit(value, MAX_VALUE_BYTES if budget is None else budget)
    if kept >= len(value):
        return value
    return {
        "elements": value[:kept],
        "elements_truncated": {"reported": kept, "total": len(value)},
    }


def bounded_plain(raw, budget=None):
    """`bounded_value(plain(raw))`, without converting the elements it is about to drop.

    `plain` is exact by contract, so it converts every element it is handed. Handing it a
    713,718-element `points` array and trimming afterwards builds seven hundred thousand
    Python objects in order to report nine hundred: 11.5 seconds, against the 66 ms that
    composing the whole stage costs. Converting under the budget instead reports the same
    elements and the same total in 28 ms.

    Use this wherever a raw USD value is on its way into a result. `bounded_value` stays
    for a value already converted — `diff_stages` compares `plain` output element by
    element and bounds only what it reports, so its values reach the bound already exact.
    """
    limit = MAX_VALUE_BYTES if budget is None else budget
    if limit is None or not _is_array(raw):
        return plain(raw)

    # Mirrors `_fit`'s accounting exactly, including its floor of one, so that what comes
    # back is what `bounded_value(plain(raw))` would have returned.
    kept = []
    spent = 0
    for item in raw:
        converted = plain(item)
        spent += len(json.dumps(converted, default=str)) + 1
        if spent > limit and kept:
            break
        kept.append(converted)

    total = len(raw)
    if len(kept) >= total:
        return kept
    return {
        "elements": kept,
        "elements_truncated": {"reported": len(kept), "total": total},
    }


def find_layer(candidates, wanted):
    """The candidate layer `wanted` names, by identifier or by resolved path, or None.

    Two callers ask this of different candidate sets — the root layer stack for an edit
    target, every used layer for a resolution anchor — and each raises its own error
    naming its own set, so only the matching itself belongs here.

    Identifiers are compared across every candidate before any path is resolved, because
    `realpath` is a syscall apiece and the ordinary caller passes back an identifier this
    package reported to it. Interleaving the two comparisons spent that round trip on
    every layer ahead of the match, and on all ~230 of them whenever the answer was no.
    """
    candidates = list(candidates)
    for layer in candidates:
        if layer.identifier == wanted:
            return layer
    resolved = os.path.realpath(wanted)
    for layer in candidates:
        if os.path.realpath(layer.identifier) == resolved:
            return layer
    return None


def layer_identifiers(stage):
    """The stage's layer stack as identifiers, strongest first.

    Every explainer that reports a layer stack wants exactly this list, so it lives next
    to `root_layer_stack` rather than being retyped at each call site. Callers still name
    their own field, because `profile_stage` calls it `root_layer_stack` and the rest call
    it `layer_stack`.
    """
    return [layer.identifier for layer in root_layer_stack(stage)]


def value_brief(value):
    """A value as it reads inside a sentence, with a long array named rather than spelled.

    The explanations are prose meant to be read. Interpolating fifty thousand floats
    into one reproduces, in the explanation, exactly the overrun `bounded_value` exists
    to prevent.

    Takes a value either side of `bounded_value`, because an explanation is usually
    built from the same dict the result reports.
    """
    if isinstance(value, dict) and "elements_truncated" in value:
        return f"an array of {value['elements_truncated']['total']} values"
    if isinstance(value, list) and _fit(value, MAX_VALUE_BYTES) < len(value):
        return f"an array of {len(value)} values"
    return repr(value)
