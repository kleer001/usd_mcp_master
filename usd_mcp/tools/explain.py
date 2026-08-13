"""Value and visibility tools."""

from typing import Any

from usd_mcp.explain import explain_value as _explain_value
from usd_mcp.explain import why_not_visible as _why_not_visible


def register(server, annotations):
    @server.tool(annotations=annotations)
    def explain_value(
        stage_path: str, prim_path: str, attribute_name: str, time_code: float | None = None
    ) -> dict[str, Any]:
        """Explain why a USD attribute resolves to the value it does.

        Returns every authored opinion in strength order — strongest first — with the
        layer that authored it and the value it holds, so a losing override can be read
        against the opinion that beat it.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
            attribute_name: attribute name, e.g. "radius" or "primvars:displayColor".
            time_code: sample a specific frame; omit for the default time code.
        """
        return _explain_value(stage_path, prim_path, attribute_name, time_code)

    @server.tool(annotations=annotations)
    def why_not_visible(
        stage_path: str, prim_path: str, load_payloads: bool = True
    ) -> dict[str, Any]:
        """Explain why a prim does not appear: missing, deactivated, an unloaded
        payload, invisible, or excluded by purpose.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
            load_payloads: set False to ask about a session that deferred payloads.
                Answering with payloads loaded about a session without them reports a
                prim as visible while the artist is looking at nothing.
        """
        return _why_not_visible(stage_path, prim_path, load_payloads)
