"""Asset resolution tool."""

from typing import Any

from usd_mcp.resolve import resolve_path as _resolve_path


def register(server, annotations):
    @server.tool(annotations=annotations)
    def resolve_path(
        stage_path: str, asset_path: str, anchor_layer: str | None = None
    ) -> dict[str, Any]:
        """Resolve an asset path the way this stage would, and report every input.

        Answers which file a reference, payload, or texture path actually names — and
        when it names nothing, reports the anchoring layer and resolver context it was
        looked up through. A relative asset path resolves against the layer that authors
        it, not the stage's root and not the working directory, which is why resolving
        one by hand so often disagrees with USD.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            asset_path: the asset path to resolve, e.g. "./tex/diffuse.exr".
            anchor_layer: the layer the path is authored in. Defaults to the stage's
                root layer. Must be a layer the stage uses.
        """
        return _resolve_path(stage_path, asset_path, anchor_layer)
