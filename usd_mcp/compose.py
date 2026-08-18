"""Composition explainers: how a prim was built, which variant it got, and where
an edit would land.

`explain.py` answers what an opinion resolved to. These answer the questions
underneath that: which arcs put the opinion in reach, which variant selection was
in force, and whether an edit aimed at a given layer would win or lose. All three
read; none authors.
"""

import os

from pxr import Usd

from usd_mcp.common import (
    bounded,
    open_stage,
    plain,
    require_attribute,
    require_prim,
    root_layer_stack,
)


def explain_prim(stage_path, prim_path):
    """Return the composition arcs that built a prim, strongest first.

    `explain_value` names the layer an opinion sits in. This names how that layer
    entered the stage at all — a reference, a payload, a variant, an inherit — which
    is what decides whether an override is even expressible from where you are.

    `composition_arcs` and `layer_stack` are bounded, strongest first; a trimmed list
    carries a companion `<field>_truncated` with the reported and total counts.
    """
    stage = open_stage(stage_path)
    prim = require_prim(stage, prim_path)

    arcs = []
    for strength, arc in enumerate(Usd.PrimCompositionQuery(prim).GetCompositionArcs()):
        introducing_layer = arc.GetIntroducingLayer()
        target_layer = arc.GetTargetLayer()
        introducing_path = str(arc.GetIntroducingPrimPath())
        arcs.append(
            {
                "strength": strength,
                "arc_type": _arc_type(arc),
                "introducing_layer": introducing_layer.identifier if introducing_layer else None,
                "introducing_prim_path": introducing_path or None,
                "target_layer": target_layer.identifier if target_layer else None,
                "target_prim_path": str(arc.GetTargetPrimPath()),
                "in_root_layer_stack": arc.IsIntroducedInRootLayerStack(),
                "has_specs": arc.HasSpecs(),
                "is_ancestral": arc.IsAncestral(),
                "is_implicit": arc.IsImplicit(),
            }
        )

    return {
        "prim": str(prim.GetPath()),
        "type_name": str(prim.GetTypeName()),
        "specifier": str(prim.GetSpecifier()),
        **bounded("composition_arcs", arcs),
        "instancing": _instancing(prim),
        **bounded("layer_stack", [layer.identifier for layer in root_layer_stack(stage)]),
    }


def explain_variants(stage_path, prim_path):
    """Return each variant set on a prim, its selection, and who authored it.

    A variant selection is prim metadata and composes like any other opinion, so a
    selection authored in a weak layer loses silently to one further up. The
    `selected_in` stack is that contest, strongest first.
    """
    stage = open_stage(stage_path)
    prim = require_prim(stage, prim_path)
    variant_sets = prim.GetVariantSets()

    sets = []
    for name in variant_sets.GetNames():
        variant_set = variant_sets.GetVariantSet(name)
        selection = variant_set.GetVariantSelection()
        sets.append(
            {
                "name": name,
                "selection": selection or None,
                "variants": list(variant_set.GetVariantNames()),
                "selected_in": _selection_opinions(prim, name),
            }
        )

    return {"prim": str(prim.GetPath()), "variant_sets": sets}


def explain_edit_target(stage_path, prim_path, attribute_name, target_layer):
    """Report whether an opinion authored in `target_layer` would win or lose.

    This is the question a write path cannot answer for itself: USD accepts an edit
    into a layer that something stronger already overrides and reports no error, so
    the value simply does not change. Asked beforehand, it is answerable — and
    answerable without authoring anything.
    """
    stage = open_stage(stage_path)
    prim = require_prim(stage, prim_path)
    attr = require_attribute(prim, attribute_name)
    layer = layer_in_root_stack(stage, target_layer)

    return {
        "prim": str(prim.GetPath()),
        "attribute": attribute_name,
        "target_layer": layer.identifier,
        "current_resolved_value": plain(attr.Get()),
        **bounded(
            "layer_stack", [candidate.identifier for candidate in root_layer_stack(stage)]
        ),
        **edit_target_verdict(prim, attr, layer),
    }


def edit_target_verdict(prim, attr, layer):
    """Whether an opinion authored in `layer` would take effect, and what stops it.

    Split out so the write path decides with the same code that explains, rather
    than with a second implementation that can drift from it.
    """
    # An instance proxy has no prim index of its own — it is a view onto the prototype —
    # so building a resolve target against it raises from deep inside USD. It also cannot
    # hold an opinion at all, which is the answer worth giving.
    if prim.IsInstanceProxy():
        return {
            "would_win": False,
            "blocked_by": "instance_proxy",
            "target_writable": _is_writable(layer),
            "outranked_by": None,
            "value_that_would_survive": None,
            "explanation": (
                f"{prim.GetPath()} is an instance proxy: it exists only through an ancestor "
                f"marked `instanceable`, and an opinion authored at this path is discarded "
                f"whatever layer it goes in. Author on the corresponding prim in the "
                f"prototype's source, or clear `instanceable` on the ancestor."
            ),
        }

    writable = _is_writable(layer)
    root_arc = Usd.PrimCompositionQuery(prim).GetCompositionArcs()[0]
    stronger = Usd.AttributeQuery(attr, root_arc.MakeResolveTargetStrongerThan(layer))

    # HasAuthoredValue, not Get: with nothing stronger authored, Get returns the
    # schema fallback, which reads as a real opinion and is not one.
    outranked = stronger.HasAuthoredValue()
    opinions = attr.GetPropertyStack(Usd.TimeCode.Default())

    # The strongest authored opinion overall. If anything at all outranks the target
    # layer, this is it — nothing can be stronger than the strongest.
    blocker = None
    if outranked and opinions:
        winner = opinions[0]
        blocker = {
            "layer": winner.layer.identifier,
            "value": plain(winner.default) if winner.HasInfo("default") else None,
        }

    # would_win answers "would an edit here take effect", which needs both a layer that
    # can be written and enough strength. Reporting strength alone sends a caller to
    # author into a package it can never save.
    blocked_by = None if writable else "read_only_layer"
    if writable and outranked:
        blocked_by = "strength"

    return {
        "would_win": blocked_by is None,
        "blocked_by": blocked_by,
        "target_writable": writable,
        "outranked_by": blocker if blocked_by == "strength" else None,
        "value_that_would_survive": plain(stronger.Get()) if outranked else None,
        "explanation": _edit_target_explanation(layer, blocked_by, blocker),
    }


def _is_writable(layer):
    """Whether scene description authored into this layer could ever be committed.

    A packaged layer — a `.usdz` and anything inside one — accepts an edit in memory
    and refuses to save it: USD raises `writing package usdz layer is not allowed`.
    Strength is beside the point when the file cannot be written at all.
    """
    return not layer.GetFileFormat().IsPackage() and layer.permissionToEdit


def _edit_target_explanation(layer, blocked_by, blocker):
    if blocked_by == "read_only_layer":
        return (
            f"{layer.identifier} cannot be authored into. It is a packaged layer, which "
            f"accepts an edit in memory and then refuses to save it. Strength is not the "
            f"problem here — pick a layer outside the package, or repackage the asset."
        )
    if blocked_by == "strength":
        return (
            f"An opinion authored in {layer.identifier} would lose and the resolved value "
            f"would not change. {blocker['layer']} already authors {blocker['value']!r} and "
            f"is stronger."
        )
    return (
        f"An opinion authored in {layer.identifier} would win: no layer stronger than it "
        f"authors this attribute."
    )


def _arc_type(arc):
    """`Pcp.ArcTypeReference` reads as `reference`."""
    return str(arc.GetArcType()).rsplit("ArcType", 1)[-1].lower()


def _instancing(prim):
    """Instancing turns an override into a silent no-op, so it is reported up front."""
    info = {
        "is_instance": prim.IsInstance(),
        "is_instance_proxy": prim.IsInstanceProxy(),
        "is_instanceable": prim.IsInstanceable(),
        "prototype": None,
        "note": None,
    }

    if prim.IsInstance():
        prototype = prim.GetPrototype()
        info["prototype"] = str(prototype.GetPath()) if prototype else None
        info["note"] = (
            "This prim is an instance. Its descendants come from the prototype, so an "
            "opinion authored on any of them is ignored. Author on the prim the instance "
            "references, or clear `instanceable` to make this branch editable."
        )
    elif prim.IsInstanceProxy():
        info["note"] = (
            "This prim is an instance proxy: it exists only through an ancestor marked "
            "`instanceable`, and an opinion authored at this path is ignored. Author on the "
            "corresponding prim in the prototype's source, or clear `instanceable` on the "
            "ancestor."
        )

    return info


def _selection_opinions(prim, variant_set_name):
    """Every layer authoring a selection for this variant set, strongest first."""
    opinions = []
    for strength, spec in enumerate(prim.GetPrimStack()):
        selection = spec.variantSelections.get(variant_set_name)
        if selection is None:
            continue
        opinions.append(
            {
                "strength": len(opinions),
                "layer": spec.layer.identifier,
                "path": str(spec.path),
                "selection": selection,
                "wins": not opinions,
                "prim_stack_index": strength,
            }
        )
    return opinions


def layer_in_root_stack(stage, target_layer):
    """Resolve `target_layer` to a layer in the stage's root layer stack.

    Refusing anything else is the point. A layer reached through a reference or a
    payload composes into some other layer stack, where "stronger" means something
    different — answering as though it were local would be a confident wrong answer
    about the exact question this server exists to get right.
    """
    candidates = root_layer_stack(stage)
    wanted = os.path.realpath(target_layer)
    for layer in candidates:
        if layer.identifier == target_layer or os.path.realpath(layer.identifier) == wanted:
            return layer
    raise ValueError(
        f"{target_layer} is not in the root layer stack of {stage.GetRootLayer().identifier}. "
        f"Layers open for an edit here: {[layer.identifier for layer in candidates]}"
    )
