"""Whether the destination host can read a stage's shading.

A renderer-specific shader survives into USD intact. `PxrSurface` and
`standard_surface` are perfectly valid scene description that any USD build will open,
parse, and show you in `usdview` — as nothing. The failure lands at the far end of a
handoff, on somebody else's schedule, and nothing warns about it beforehand.

USD's own answer is the render context: a material carries one terminal output per
context — `outputs:surface` for the universal one, `outputs:ri:surface` for RenderMan,
`outputs:arnold:surface` for Arnold — and a host reads the one it recognises. So the
question "can the destination read this" is answerable from the scene description, and
this asks it: which contexts each material provides for, what the target would actually
resolve to, and whether the network behind it is the portable `UsdPreviewSurface` set or
something only one renderer knows.

Reads only.
"""

from pxr import Sdr, UsdShade

from usd_mcp.common import open_stage

# Render context tokens, each verified against a primary source rather than inferred:
# `ri` is `UsdRi.Tokens.renderContext` in USD itself; `glslfx` appears in USD's render
# user guide as `outputs:glslfx:surface`; `arnold` is `outputs:arnold:surface` in
# arnold-usd; `mtlx` is the MaterialX context in USD's MaterialX architecture guide.
# The empty token is `UsdShade.Tokens.universalRenderContext`.
#
# An unrecognised target is refused rather than passed through as a token. A context
# nobody verified would produce a confident answer about a host this cannot speak for,
# and a wrong answer here is discovered after the handoff.
TARGETS = {
    "preview": "",
    "universal": "",
    "usdview": "",
    "storm": "glslfx",
    "glslfx": "glslfx",
    "renderman": "ri",
    "prman": "ri",
    "ri": "ri",
    "arnold": "arnold",
    "materialx": "mtlx",
    "mtlx": "mtlx",
}

# The UsdPreviewSurface specification's complete node set — the shading every USD host
# is expected to read. `test_portability.py` pins this against the shader registry, so a
# node added to the spec fails the build rather than quietly reading as unportable.
PREVIEW_SURFACE_NODES = frozenset(
    {
        "UsdPreviewSurface",
        "UsdUVTexture",
        "UsdTransform2d",
        "UsdPrimvarReader_float",
        "UsdPrimvarReader_float2",
        "UsdPrimvarReader_float3",
        "UsdPrimvarReader_float4",
        "UsdPrimvarReader_int",
        "UsdPrimvarReader_matrix",
        "UsdPrimvarReader_normal",
        "UsdPrimvarReader_point",
        "UsdPrimvarReader_string",
        "UsdPrimvarReader_vector",
    }
)

_TERMINALS = {
    "surface": UsdShade.Material.ComputeSurfaceSource,
    "displacement": UsdShade.Material.ComputeDisplacementSource,
    "volume": UsdShade.Material.ComputeVolumeSource,
}

# Four things can happen to a material at the far end of a handoff, and the worst one
# across a material's terminals is the material's verdict.
#
# `native`             the target's own context is authored, or the universal network is
#                      the portable set and the target reads the universal context.
# `preview_fallback`   nothing authored for the target; it falls back to a universal
#                      output that is UsdPreviewSurface throughout. Renders, but not as
#                      the look that was authored.
# `renderer_specific`  it falls back to a universal output wired to shaders outside the
#                      portable set. Whether the target reads them depends on plugins
#                      this cannot see — and a universal output is promising a
#                      portability it may not have.
# `unreadable`         nothing resolves for the target at all.
_SEVERITY = {"native": 0, "preview_fallback": 1, "renderer_specific": 2, "unreadable": 3}


def check_portability(stage_path, target):
    """Report what `target` would resolve for each material, and what it would miss.

    `target` names a render context: a host name this knows (`renderman`, `arnold`,
    `storm`, `materialx`, `preview`) or the context token itself (`ri`, `glslfx`,
    `arnold`, `mtlx`, or the empty string for the universal context). Anything else
    raises rather than guess at a context nobody verified.
    """
    context = _resolve_target(target)
    stage = open_stage(stage_path)

    materials = [
        _material_report(UsdShade.Material(prim), context)
        for prim in stage.Traverse()
        if UsdShade.Material(prim)
    ]

    summary = {"materials": len(materials)}
    summary.update(
        {verdict: sum(1 for m in materials if m["verdict"] == verdict) for verdict in _SEVERITY}
    )

    return {
        "stage": stage_path,
        "target": target,
        "render_context": context,
        "readable": summary["unreadable"] == 0 and summary["renderer_specific"] == 0,
        "materials": materials,
        "summary": summary,
        "findings": _findings(materials, summary, context),
    }


def _resolve_target(target):
    if target not in TARGETS:
        raise ValueError(
            f"unknown target {target!r}. Known targets: {sorted(TARGETS)}. A render "
            f"context not listed here has not been verified against a primary source; "
            f"adding one means adding its token deliberately."
        )
    return TARGETS[target]


def _material_report(material, context):
    terminals = {}
    for name, compute in _TERMINALS.items():
        report = _terminal_report(material, name, compute, context)
        if report is not None:
            terminals[name] = report

    verdict = (
        max((t["verdict"] for t in terminals.values()), key=_SEVERITY.__getitem__)
        if terminals
        else "unreadable"
    )

    return {
        "material": str(material.GetPrim().GetPath()),
        "verdict": verdict,
        "contexts": sorted(_authored_contexts(material)),
        "terminals": terminals,
        "explanation": _explanation(material, verdict, terminals, context),
    }


def _terminal_report(material, name, compute, context):
    """One terminal's verdict, or None when nothing resolves for the target at all."""
    own_name = f"{context}:{name}" if context else name
    own = material.GetOutput(own_name)
    # USD creates an output on request, so its existence is not a provision. A connected
    # source is. `ComputeSurfaceSource` already falls back to the universal context, which
    # is the behaviour being reported here rather than the thing to detect it with.
    has_own = bool(own) and own.HasConnectedSource()

    source = compute(material, context if has_own else UsdShade.Tokens.universalRenderContext)[0]
    if not source:
        return None

    shaders = _network(source)
    unportable = [entry for entry in shaders if entry["id"] not in PREVIEW_SURFACE_NODES]

    if has_own and context:
        # The author wired a network to this context's own output and so declared it
        # readable there. Shaders outside the portable set are the point, not a problem.
        verdict = "native"
    elif unportable:
        verdict = "renderer_specific"
    elif context:
        verdict = "preview_fallback"
    else:
        verdict = "native"

    return {
        "terminal": name,
        "verdict": verdict,
        "resolved_from_universal": bool(context) and not has_own,
        "source": str(source.GetPrim().GetPath()),
        "shaders": shaders,
        "unportable_shaders": [entry["id"] for entry in unportable],
    }


def _authored_contexts(material):
    """Every render context this material authors a terminal output for.

    `outputs:ri:surface` is namespaced by context and `outputs:surface` is not, so the
    base name carries the answer. An unconnected output is not a provision — USD creates
    one on request and a caller that stopped there authored nothing.
    """
    contexts = set()
    for output in material.GetOutputs():
        if not output.HasConnectedSource():
            continue
        name = output.GetBaseName()
        contexts.add(name.rsplit(":", 1)[0] if ":" in name else "")
    return contexts


def _network(source):
    """Every shader reachable from a terminal source, following its connections.

    A node graph in the middle of a network has no shader id of its own; it is walked
    through rather than reported, so the list is the shaders a renderer must recognise.
    """
    registry = Sdr.Registry()
    found = {}
    stack = [UsdShade.ConnectableAPI(source.GetPrim())]

    while stack:
        node = stack.pop()
        path = str(node.GetPrim().GetPath())
        if path in found:
            continue

        shader = UsdShade.Shader(node.GetPrim())
        found[path] = (
            {
                "prim": path,
                "id": shader.GetShaderId(),
                "registered_here": bool(
                    registry.GetShaderNodeByIdentifier(shader.GetShaderId())
                ),
            }
            if shader
            else None
        )

        for port in list(node.GetInputs()) + list(node.GetOutputs()):
            for info in port.GetConnectedSources()[0]:
                stack.append(info.source)

    return sorted((entry for entry in found.values() if entry), key=lambda e: e["prim"])


def _context_name(context):
    return context or "the universal context"


def _explanation(material, verdict, terminals, context):
    path = material.GetPrim().GetPath()
    named = _context_name(context)

    if not terminals:
        authored = sorted(_authored_contexts(material))
        if authored:
            return (
                f"{path} authors terminal outputs only for "
                f"{', '.join(_context_name(name) for name in authored)}, which {named} "
                f"does not read, and no universal output to fall back to. A host reading "
                f"{named} finds nothing to resolve."
            )
        return (
            f"{path} authors no connected terminal output at all, in any render context. "
            f"Nothing will render it."
        )
    if verdict == "native":
        return f"{path} provides a network for {named} and resolves to it directly."
    if verdict == "preview_fallback":
        return (
            f"{path} authors nothing for {named}, so a host reading that context falls "
            f"back to the universal output. That network is UsdPreviewSurface throughout, "
            f"so it renders — as a preview surface, not as the look that was authored."
        )

    unportable = sorted(
        {shader for report in terminals.values() for shader in report["unportable_shaders"]}
    )
    return (
        f"{path} resolves {named} through its universal output, which is wired to "
        f"{', '.join(unportable)} rather than to the UsdPreviewSurface set. Whether the "
        f"target reads those shaders depends on plugins this cannot see; a universal "
        f"output is claiming a portability it may not have."
    )


def _findings(materials, summary, context):
    findings = []
    named = _context_name(context)

    for verdict, note in (
        (
            "unreadable",
            f"resolve to nothing at all for {named}. Author a terminal for this context or "
            f"bind a "
            f"UsdPreviewSurface network to the universal output before handing the "
            f"stage over.",
        ),
        (
            "renderer_specific",
            "fall back to a universal output wired outside the UsdPreviewSurface set. "
            "They render only if the destination has those shaders.",
        ),
        (
            "preview_fallback",
            f"have no network for {named} and fall back to UsdPreviewSurface. They "
            f"render, but not as authored.",
        ),
    ):
        count = summary[verdict]
        if not count:
            continue
        paths = [m["material"] for m in materials if m["verdict"] == verdict]
        findings.append(
            f"{count} of {summary['materials']} materials {note} ({', '.join(paths)})"
        )

    unregistered = sorted(
        {
            shader["id"]
            for material in materials
            for report in material["terminals"].values()
            for shader in report["shaders"]
            if not shader["registered_here"]
        }
    )
    if unregistered:
        findings.append(
            f"Shader ids no plugin in this USD build defines: {', '.join(unregistered)}. "
            f"Their inputs cannot be validated here, only their presence."
        )

    return findings
