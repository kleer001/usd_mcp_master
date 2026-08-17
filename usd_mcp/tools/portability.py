"""Shading portability tool."""

from typing import Any

from usd_mcp.portability import check_portability as _check_portability


def register(server, annotations):
    @server.tool(annotations=annotations)
    def check_portability(stage_path: str, target: str) -> dict[str, Any]:
        """Report whether the destination host can read this stage's shading.

        A renderer-specific shader survives into USD intact and means nothing at the far
        end of a handoff, with no warning beforehand. USD's answer is the render context:
        a material carries one terminal output per context, and a host reads the one it
        recognises. This reports, per material, what the target would actually resolve —
        its own network, a fallback to UsdPreviewSurface, a fallback to shaders only some
        renderers have, or nothing at all.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            target: the destination render context. A host name — "renderman", "arnold",
                "storm", "materialx", "preview" — or the context token itself: "ri",
                "arnold", "glslfx", "mtlx", or "universal" for the universal context. An
                unrecognised target raises rather than guess at an unverified context.
        """
        return _check_portability(stage_path, target)
