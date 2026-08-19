"""Where a stage's cost sits: layers, payloads, instancing, and time.

A stage that opens slowly rarely says why. The expensive facts are countable but
scattered — how many prim specs each layer contributes, how much of the scene is
instanced, how many payloads were deferred, and how much of the animation is animation
at all. This gathers them in one pass and names the traps that follow from them.

The one worth naming out loud: an attribute authored with time samples makes everything
downstream of it time-dependent, whether or not the samples differ. A file path written
once per frame costs a re-cook per frame and buys nothing, and nothing in USD warns about
it because nothing in USD is wrong.

Reads only, and composes no more than the caller asked for: `load_payloads=False`
profiles the stage as a session that deferred them sees it.
"""

from pxr import Usd

from usd_mcp.common import (
    bounded,
    layer_identifiers,
    open_stage,
    prim_specs,
)

# The default predicate also demands `PrimIsLoaded`, which hides the very prims a
# payload profile is about: an unloaded payload's own prim, not just its contents.
# Instance proxies are included because on an instanced set they are most of the scene.
_PROFILED_PRIMS = Usd.TraverseInstanceProxies(
    Usd.PrimIsActive & Usd.PrimIsDefined & ~Usd.PrimIsAbstract
)


def profile_stage(stage_path, load_payloads=True):
    """Return the layer, payload, instancing, and time profile of a stage.

    `load_payloads` must match the session being asked about. Profiling with payloads
    loaded reports a scene the artist who deferred them is not paying for.

    `layers` and `root_layer_stack` are bounded; a stage of a few hundred layers would
    otherwise spend the whole answer listing them. `layers` is sorted by prim specs
    descending, so what survives the bound is what costs the most to read. Every
    aggregate under `time` is summed over all layers, bound or not.
    """
    stage = open_stage(stage_path, load_payloads=load_payloads)

    layers = sorted(
        (
            _layer_profile(layer)
            for layer in stage.GetUsedLayers()
            if layer != stage.GetSessionLayer()
        ),
        key=lambda entry: (-entry["prim_specs"], entry["layer"]),
    )
    prims = _prim_profile(stage)
    time = _time_profile(stage, layers)

    return {
        "stage": stage_path,
        "payloads_loaded": load_payloads,
        **bounded(
            "root_layer_stack", layer_identifiers(stage)
        ),
        **bounded("layers", layers),
        "prims": prims,
        "instancing": _instancing_profile(stage, prims),
        "time": time,
        # Findings read every layer, not the bounded slice: the layer holding the most
        # constant-valued samples is worth naming whether or not it made the cut.
        "findings": _findings(prims, time, layers),
    }


def _layer_profile(layer):
    """Prim, attribute, and time sample specs one layer authors, composition aside.

    Counted from scene description rather than from the composed stage: the question is
    what this file costs to read, and a layer contributes its specs whether or not
    anything stronger overrides them. Variant contents count — they are in the file.
    """
    counts = {"prim_specs": 0, "attribute_specs": 0, "time_sampled_specs": 0, "constant": 0}

    for spec in prim_specs(layer):
        counts["prim_specs"] += 1
        for attribute in spec.attributes:
            counts["attribute_specs"] += 1
            times = layer.ListTimeSamplesForPath(attribute.path)
            if not times:
                continue
            counts["time_sampled_specs"] += 1
            if _samples_never_change(layer, attribute.path, times):
                counts["constant"] += 1

    return {
        "layer": layer.identifier,
        "prim_specs": counts["prim_specs"],
        "attribute_specs": counts["attribute_specs"],
        "time_sampled_specs": counts["time_sampled_specs"],
        "constant_time_sampled_specs": counts["constant"],
    }


def _samples_never_change(layer, path, times):
    """Whether every sample at this path holds the same value as the first."""
    first = layer.QueryTimeSample(path, times[0])
    return all(layer.QueryTimeSample(path, time) == first for time in times[1:])


def _prim_profile(stage):
    """Composed prim counts, instance proxies and unloaded payload prims included.

    A prim inside an unloaded payload is genuinely absent and is not counted. The prim
    carrying the payload is not — it composed, it just brought nothing with it, and it
    is the one worth reporting.
    """
    counts = {
        "total": 0,
        "instance_proxies": 0,
        "instances": 0,
        "instanceable": 0,
        "with_payload": 0,
        "unloaded_payloads": 0,
    }

    for prim in stage.Traverse(_PROFILED_PRIMS):
        counts["total"] += 1
        if prim.IsInstanceProxy():
            counts["instance_proxies"] += 1
        if prim.IsInstance():
            counts["instances"] += 1
        if prim.IsInstanceable():
            counts["instanceable"] += 1
        if prim.HasAuthoredPayloads():
            counts["with_payload"] += 1
            if not prim.IsLoaded():
                counts["unloaded_payloads"] += 1

    return counts


def _instancing_profile(stage, prims):
    """How much of the scene is shared rather than composed prim by prim."""
    prototypes = stage.GetPrototypes()
    return {
        "prototypes": len(prototypes),
        "instances": prims["instances"],
        "instanceable_prims": prims["instanceable"],
        "instance_proxies": prims["instance_proxies"],
        "proxy_share": (
            round(prims["instance_proxies"] / prims["total"], 4) if prims["total"] else 0.0
        ),
    }


def _time_profile(stage, layers):
    return {
        "has_authored_range": stage.HasAuthoredTimeCodeRange(),
        "start_time_code": stage.GetStartTimeCode(),
        "end_time_code": stage.GetEndTimeCode(),
        "time_codes_per_second": stage.GetTimeCodesPerSecond(),
        "time_sampled_specs": sum(entry["time_sampled_specs"] for entry in layers),
        "constant_time_sampled_specs": sum(
            entry["constant_time_sampled_specs"] for entry in layers
        ),
    }


def _specs(count, singular_verb, plural_verb):
    """`3 attribute specs carry`, `1 attribute spec carries`."""
    noun = "attribute spec" if count == 1 else "attribute specs"
    return f"{count} {noun} {singular_verb if count == 1 else plural_verb}"


def _findings(prims, time, layers):
    """The traps the numbers imply, said in words, or an empty list."""
    findings = []

    constant = time["constant_time_sampled_specs"]
    if constant:
        worst = max(layers, key=lambda entry: entry["constant_time_sampled_specs"])
        findings.append(
            f"{_specs(constant, 'carries', 'carry')} time samples whose value never "
            f"changes. Each one makes everything downstream of it time-dependent and buys "
            f"nothing; {worst['layer']} holds {worst['constant_time_sampled_specs']} of them."
        )

    if time["time_sampled_specs"] and not time["has_authored_range"]:
        findings.append(
            f"{_specs(time['time_sampled_specs'], 'is', 'are')} time sampled, but the "
            f"stage authors no startTimeCode or endTimeCode. A client has no frame range to "
            f"play and will fall back to {time['start_time_code']} to "
            f"{time['end_time_code']}."
        )

    if prims["unloaded_payloads"]:
        findings.append(
            f"Payloads not loaded: {prims['unloaded_payloads']} of "
            f"{prims['with_payload']}. Prims inside them are absent from every count here; "
            f"profile with load_payloads=true for the full scene."
        )

    return findings
