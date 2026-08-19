"""Asset resolution: which file an asset path actually names, and why not.

Composition explains which opinion won. Resolution explains whether the file
holding it was found at all — a different failure with the same symptom, and the
one that produces "it works on my machine". The documented way to investigate is
`TF_DEBUG=AR_RESOLVER_INIT` and reading log spew; this reports the same facts as
a value.
"""

import os

from pxr import Ar

from usd_mcp.common import find_layer, open_stage


def resolve_path(stage_path, asset_path, anchor_layer=None):
    """Resolve an asset path the way the stage would, and report every input.

    An asset path means nothing on its own. It resolves against an anchoring layer
    and a resolver context, and both come from the stage — which is why resolving
    by hand in a shell so often disagrees with what USD does.
    """
    stage = open_stage(stage_path)
    anchor = _anchor_layer(stage, anchor_layer)
    context = stage.GetPathResolverContext()
    resolver = Ar.GetResolver()

    with Ar.ResolverContextBinder(context):
        identifier = resolver.CreateIdentifier(asset_path, Ar.ResolvedPath(anchor.identifier))
        resolved = resolver.Resolve(identifier).GetPathString()

    return {
        "asset_path": asset_path,
        "anchor_layer": anchor.identifier,
        "resolver": type(Ar.GetUnderlyingResolver()).__name__,
        "resolver_context": str(context),
        "identifier": identifier,
        "resolved_path": resolved or None,
        "resolved": bool(resolved),
        "exists": bool(resolved) and os.path.isfile(resolved),
        "explanation": _explanation(asset_path, anchor, context, resolved),
    }


def _explanation(asset_path, anchor, context, resolved):
    if resolved:
        return f"{asset_path} anchored at {anchor.identifier} resolves to {resolved}."
    return (
        f"{asset_path} does not resolve. It was anchored at {anchor.identifier} and looked "
        f"up through {context}. A relative path resolves against the layer that authors it, "
        f"not the stage's root layer and not the working directory — check which layer holds "
        f"this path before assuming the file is missing."
    )


def _anchor_layer(stage, anchor_layer):
    """The layer the asset path is anchored to; the root layer when unspecified.

    Any layer the stage uses is a legitimate anchor, not just the root layer stack:
    a path authored inside a referenced asset anchors to that asset's layer, and
    resolving it against the root would answer a question nobody asked.
    """
    if anchor_layer is None:
        return stage.GetRootLayer()

    used = stage.GetUsedLayers()
    layer = find_layer(used, anchor_layer)
    if layer is not None:
        return layer
    raise ValueError(
        f"{anchor_layer} is not a layer used by {stage.GetRootLayer().identifier}. "
        f"Layers it uses: {sorted(candidate.identifier for candidate in used)}"
    )
