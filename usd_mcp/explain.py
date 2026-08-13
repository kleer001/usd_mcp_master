"""Composition explainers: why an attribute has the value it has, and why a prim
is not visible.

Pure functions over a USD stage path. Nothing here mutates a stage, opens a
socket, or writes a file. Every function returns plain dicts so the MCP layer can
serialise them without a translation step.
"""

from pxr import Sdf, Usd, UsdGeom

# Visibility and purpose inherit down namespace, so the answer to "why is this
# invisible" is usually authored on an ancestor, not on the prim asked about.
_INHERITED_CHECKS = ("visibility", "purpose")


def open_stage(stage_path):
    stage = Usd.Stage.Open(stage_path)
    if not stage:
        raise ValueError(f"could not open as a USD stage: {stage_path}")
    return stage


def explain_value(stage_path, prim_path, attribute_name, time_code=None):
    """Return every authored opinion for an attribute, strongest first.

    The winning opinion is index 0. Losing opinions carry their own value, which
    is the question a sparse override actually raises: not "what is it" but
    "what did mine lose to".
    """
    stage = open_stage(stage_path)
    prim = _require_prim(stage, prim_path)
    attr = prim.GetAttribute(attribute_name)
    if not attr:
        raise ValueError(f"{prim_path} has no attribute {attribute_name!r}")

    tc = Usd.TimeCode.Default() if time_code is None else Usd.TimeCode(time_code)
    stack = attr.GetPropertyStack(tc)
    opinions = [_describe_spec(spec) for spec in stack]
    for i, opinion in enumerate(opinions):
        opinion["strength"] = i
        opinion["wins"] = i == 0

    resolve_info = attr.GetResolveInfo(tc)
    return {
        "prim": str(prim.GetPath()),
        "attribute": attribute_name,
        "type_name": str(attr.GetTypeName()),
        "resolved_value": _plain(attr.Get(tc)),
        "resolved_from": str(resolve_info.GetSource()),
        "time_code": "default" if time_code is None else time_code,
        "authored_opinions": opinions,
        "layer_stack": [layer.identifier for layer in stage.GetLayerStack()],
    }


def why_not_visible(stage_path, prim_path):
    """Diagnose an absent or unrendered prim.

    Covers the four ways a prim disappears without an error: it was never
    composed, an ancestor is deactivated, visibility is authored `invisible`
    somewhere up the chain, or its purpose excludes it from a default render.
    """
    stage = open_stage(stage_path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        return _explain_missing_prim(stage, prim_path)

    reasons = []
    checks = {"exists": True, "active": prim.IsActive(), "loaded": prim.IsLoaded()}

    if not prim.IsActive():
        reasons.append(
            f"{prim_path} is deactivated; its descendants are not composed at all. "
            f"{_authored_in(prim, 'active')}"
        )
    if prim.HasAuthoredPayloads() and not prim.IsLoaded():
        reasons.append(f"{prim_path} has an unloaded payload, so its contents are absent.")

    imageable = UsdGeom.Imageable(prim)
    if not imageable:
        checks["imageable"] = False
        reasons.append(f"{prim_path} is type {prim.GetTypeName() or '<untyped>'}, not an Imageable.")
        return {"prim": prim_path, "visible": False, "reasons": reasons, "checks": checks}

    checks["imageable"] = True
    visibility = imageable.ComputeVisibility()
    purpose = imageable.ComputePurpose()
    checks["computed_visibility"] = str(visibility)
    checks["computed_purpose"] = str(purpose)

    if visibility == UsdGeom.Tokens.invisible:
        blockers = _invisible_ancestry(prim)
        for blocker in blockers:
            reasons.append(
                f"visibility=invisible on {blocker['prim']} — {blocker['authored_in']}"
            )
        if not blockers:
            reasons.append("computed visibility is invisible but no authored opinion was found.")

    if purpose not in (UsdGeom.Tokens.default_, UsdGeom.Tokens.render):
        reasons.append(
            f"purpose={purpose}; a default render pass draws only `default` and `render`. "
            f"{_authored_in(prim, 'purpose')}"
        )

    return {
        "prim": prim_path,
        "visible": not reasons,
        "reasons": reasons,
        "checks": checks,
    }


def _require_prim(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"no prim at {prim_path}")
    return prim


def _describe_spec(spec):
    layer = spec.layer
    owner = layer.GetPrimAtPath(spec.path.GetPrimPath())
    has_default = spec.HasInfo("default")
    return {
        "layer": layer.identifier,
        "path": str(spec.path),
        "specifier": str(owner.specifier) if owner else None,
        "has_default": has_default,
        "value": _plain(spec.default) if has_default else None,
        "time_samples": layer.GetNumTimeSamplesForPath(spec.path),
    }


def _explain_missing_prim(stage, prim_path):
    """Walk root-down to the point the path stops composing and name the cause."""
    deepest = stage.GetPseudoRoot()
    for name in Sdf.Path(prim_path).GetPrefixes():
        candidate = stage.GetPrimAtPath(name)
        if not candidate:
            return {
                "prim": prim_path,
                "visible": False,
                "reasons": [
                    f"{prim_path} does not exist on this stage. The path composes as far as "
                    f"{deepest.GetPath()} and stops: {name} is not defined there"
                    + (
                        f", and {deepest.GetPath()} is deactivated, so nothing below it composes."
                        if deepest != stage.GetPseudoRoot() and not deepest.IsActive()
                        else "."
                    )
                ],
                "checks": {"exists": False, "deepest_existing": str(deepest.GetPath())},
            }
        deepest = candidate
    raise AssertionError(f"{prim_path} resolved on the second pass; stage changed underneath us")


def _invisible_ancestry(prim):
    """Every prim from the root down that authors visibility=invisible."""
    blockers = []
    for ancestor in reversed(list(_self_and_ancestors(prim))):
        imageable = UsdGeom.Imageable(ancestor)
        if not imageable:
            continue
        attr = imageable.GetVisibilityAttr()
        if attr.HasAuthoredValue() and attr.Get() == UsdGeom.Tokens.invisible:
            blockers.append(
                {"prim": str(ancestor.GetPath()), "authored_in": _authored_in(ancestor, "visibility")}
            )
    return blockers


def _self_and_ancestors(prim):
    while prim and prim.GetPath() != Sdf.Path.absoluteRootPath:
        yield prim
        prim = prim.GetParent()


def _authored_in(prim, attribute_name):
    attr = prim.GetAttribute(attribute_name)
    if not attr:
        return f"no authored `{attribute_name}` opinion."
    stack = attr.GetPropertyStack(Usd.TimeCode.Default())
    if not stack:
        return f"no authored `{attribute_name}` opinion."
    return "authored in " + ", ".join(spec.layer.identifier for spec in stack)


def _plain(value):
    """USD values are C++ types; JSON needs Python ones."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "__len__") and not isinstance(value, str):
        return [_plain(item) for item in value]
    return str(value)
