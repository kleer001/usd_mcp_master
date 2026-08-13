"""Composition arc, variant, and edit-target tools."""

from typing import Any

from usd_mcp.compose import explain_edit_target as _explain_edit_target
from usd_mcp.compose import explain_prim as _explain_prim
from usd_mcp.compose import explain_variants as _explain_variants


def register(server, annotations):
    @server.tool(annotations=annotations)
    def explain_prim(stage_path: str, prim_path: str) -> dict[str, Any]:
        """Explain how a prim was composed: the arcs that built it, strongest first.

        Each arc reports its kind — reference, payload, variant, inherit, specialize,
        root — the layer that introduced it and the layer and path it targets. Use this
        when an override is not expressible from where you are: the arc a prim arrives
        through decides where an opinion about it can be authored at all.

        Also reports instancing, because an opinion authored on an instance proxy is
        discarded with no error.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
        """
        return _explain_prim(stage_path, prim_path)

    @server.tool(annotations=annotations)
    def explain_variants(stage_path: str, prim_path: str) -> dict[str, Any]:
        """Explain which variant is selected on a prim and which layer selected it.

        A variant selection composes like any other opinion, so an asset's own default
        can be overridden by a shot layer — or a shot layer's selection can lose to
        something stronger. Returns each variant set, its available variants, the
        selection in force, and every layer authoring a selection, strongest first.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
        """
        return _explain_variants(stage_path, prim_path)

    @server.tool(annotations=annotations)
    def explain_edit_target(
        stage_path: str, prim_path: str, attribute_name: str, target_layer: str
    ) -> dict[str, Any]:
        """Report whether an edit authored in a given layer would win or silently lose.

        USD accepts an opinion authored into a layer that something stronger already
        overrides, raises no error, and leaves the resolved value unchanged. Ask this
        before authoring: it reports whether the target layer is strong enough, and
        names the layer and value that would outrank it if not.

        The target layer must be in the stage's root layer stack. A layer reached
        through a reference or payload composes elsewhere and is refused rather than
        guessed at.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
            attribute_name: attribute name, e.g. "radius".
            target_layer: path to the layer the edit would be authored in.
        """
        return _explain_edit_target(stage_path, prim_path, attribute_name, target_layer)
