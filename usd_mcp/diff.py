"""Structural diff between two stages, with numeric tolerance.

`usddiff` runs both files through `usdcat` and hands the text to `diff`, so it reports
a re-export's float noise and a real edit as the same thing. This compares scene
description rather than its serialisation: prims added, removed, and retyped, and
attribute values compared number by number against a tolerance the caller sets.

Two scopes, because they answer different questions. `composed` opens both stages and
compares what they resolve to — the shot as an artist sees it, sublayers, references,
payloads, variants and all. `layer` opens one file each as authored and compares only
what that file says, which is the question when a layer was re-exported and the stage
around it did not change.

Reads only. Nothing here opens a stage for editing or touches a layer's contents.
"""

from pxr import Usd

from usd_mcp.common import open_layer, open_stage, plain

SCOPES = ("composed", "layer")

# Stage.Traverse() skips instance proxies, and a change inside an instanced asset lives
# nowhere else on a composed stage — reporting two such stages as identical would be a
# confident wrong answer. Proxies are cheap to skip and expensive to miss.
_ALL_PRIMS = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)


def diff_stages(stage_a, stage_b, tolerance=0.0, scope="composed"):
    """Report how two stages differ, ignoring numeric differences within `tolerance`.

    `tolerance` is an absolute bound applied to every number compared — attribute
    values, vector and matrix components, array elements, and time sample times. Zero
    means exact equality. Differences it absorbs are counted in `counts.within_tolerance`
    rather than discarded silently: that count is the answer to "was this a real edit or
    a re-export".
    """
    if tolerance < 0:
        raise ValueError(f"tolerance must not be negative: {tolerance}")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}: {scope!r}")

    snapshot = _composed_prims if scope == "composed" else _layer_prims
    prims_a = snapshot(stage_a)
    prims_b = snapshot(stage_b)
    result = _compare(prims_a, prims_b, tolerance)
    within_tolerance = result.pop("within_tolerance")

    return {
        "stage_a": stage_a,
        "stage_b": stage_b,
        "scope": scope,
        "tolerance": tolerance,
        **result,
        "counts": {
            "prims_a": len(prims_a),
            "prims_b": len(prims_b),
            "added": len(result["prims_added"]),
            "removed": len(result["prims_removed"]),
            "retyped": len(result["prims_retyped"]),
            "attributes_changed": len(result["attributes_changed"]),
            "within_tolerance": within_tolerance,
        },
    }


def _compare(prims_a, prims_b, tolerance):
    added = [
        {"path": path, "type_name": prims_b[path]["type_name"]}
        for path in sorted(set(prims_b) - set(prims_a))
    ]
    removed = [
        {"path": path, "type_name": prims_a[path]["type_name"]}
        for path in sorted(set(prims_a) - set(prims_b))
    ]

    retyped = []
    changed = []
    within_tolerance = 0

    for path in sorted(set(prims_a) & set(prims_b)):
        prim_a, prim_b = prims_a[path], prims_b[path]
        if prim_a["type_name"] != prim_b["type_name"]:
            retyped.append(
                {
                    "path": path,
                    "type_name_a": prim_a["type_name"],
                    "type_name_b": prim_b["type_name"],
                }
            )

        names = set(prim_a["attributes"]) | set(prim_b["attributes"])
        for name in sorted(names):
            attr_a = prim_a["attributes"].get(name)
            attr_b = prim_b["attributes"].get(name)
            if attr_a is not None and attr_b is not None and _equal(attr_a, attr_b, tolerance):
                if tolerance and not _equal(attr_a, attr_b, 0.0):
                    within_tolerance += 1
                continue
            changed.append(_change(path, name, attr_a, attr_b, tolerance))

    return {
        "identical": not (added or removed or retyped or changed),
        "prims_added": added,
        "prims_removed": removed,
        "prims_retyped": retyped,
        "attributes_changed": changed,
        "within_tolerance": within_tolerance,
    }


def _change(prim_path, name, attr_a, attr_b, tolerance):
    """One reported difference, with the animation summarised rather than dumped.

    A thousand-sample attribute is compared sample by sample but reported as its sample
    counts and the first time they part company — enough to find the change, short
    enough to read.
    """
    times_a = attr_a["times"] if attr_a else []
    times_b = attr_b["times"] if attr_b else []
    return {
        "prim": prim_path,
        "attribute": name,
        "authored_a": attr_a is not None,
        "authored_b": attr_b is not None,
        "value_a": attr_a["default"] if attr_a else None,
        "value_b": attr_b["default"] if attr_b else None,
        "time_samples": (
            {
                "count_a": len(times_a),
                "count_b": len(times_b),
                "first_differing_time": _first_differing_time(attr_a, attr_b, tolerance),
            }
            if times_a or times_b
            else None
        ),
    }


def _first_differing_time(attr_a, attr_b, tolerance):
    """The earliest sample time where the two series part, or null if they agree."""
    times_a = attr_a["times"] if attr_a else []
    times_b = attr_b["times"] if attr_b else []
    samples_a = attr_a["samples"] if attr_a else []
    samples_b = attr_b["samples"] if attr_b else []

    for index in range(min(len(times_a), len(times_b))):
        if not _equal(times_a[index], times_b[index], tolerance):
            return min(times_a[index], times_b[index])
        if not _equal(samples_a[index], samples_b[index], tolerance):
            return times_a[index]

    longer = times_a if len(times_a) > len(times_b) else times_b
    shorter_length = min(len(times_a), len(times_b))
    return longer[shorter_length] if len(longer) > shorter_length else None


def _equal(left, right, tolerance):
    """Structural equality, with every number compared against `tolerance`.

    Both sides arrive through `plain()`, so a matrix is nested lists and an asset path
    is a dict — one recursion covers every USD value type without a per-type branch.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(left - right) <= tolerance
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _equal(left[key], right[key], tolerance) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _equal(one, other, tolerance) for one, other in zip(left, right, strict=True)
        )
    return left == right


def _composed_prims(stage_path):
    """Every composed prim and its authored attributes, keyed by path."""
    stage = open_stage(stage_path)
    prims = {}
    for prim in stage.Traverse(_ALL_PRIMS):
        prims[str(prim.GetPath())] = {
            "type_name": str(prim.GetTypeName()),
            "attributes": {
                attr.GetName(): _composed_attribute(attr)
                for attr in prim.GetAuthoredAttributes()
            },
        }
    return prims


def _composed_attribute(attr):
    times = list(attr.GetTimeSamples())
    return {
        "default": plain(attr.Get(Usd.TimeCode.Default())),
        "times": times,
        "samples": [plain(attr.Get(time)) for time in times],
    }


def _layer_prims(layer_path):
    """Every prim spec in one layer as authored, keyed by path."""
    layer = open_layer(layer_path)
    prims = {}

    def walk(spec):
        prims[str(spec.path)] = {
            "type_name": spec.typeName,
            "attributes": {
                attr.name: _layer_attribute(layer, attr) for attr in spec.attributes
            },
        }
        for child in spec.nameChildren:
            walk(child)

    for root in layer.rootPrims:
        walk(root)
    return prims


def _layer_attribute(layer, spec):
    times = list(layer.ListTimeSamplesForPath(spec.path))
    return {
        "default": plain(spec.default) if spec.HasInfo("default") else None,
        "times": times,
        "samples": [plain(layer.QueryTimeSample(spec.path, time)) for time in times],
    }
