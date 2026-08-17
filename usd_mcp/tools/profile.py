"""Stage profiling tool."""

from typing import Any

from usd_mcp.profile import profile_stage as _profile_stage


def register(server, annotations):
    @server.tool(annotations=annotations)
    def profile_stage(stage_path: str, load_payloads: bool = True) -> dict[str, Any]:
        """Report where a stage's cost sits: layers, payloads, instancing, and time.

        Returns prim and attribute specs per layer, payload and instancing coverage, the
        stage's frame range, and a findings list naming the traps the numbers imply. Chief
        among them: an attribute authored with time samples makes everything downstream of
        it time-dependent whether or not the samples differ, so a file path written once
        per frame costs a re-cook per frame and buys nothing.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            load_payloads: compose payload contents. Set false to profile the stage as a
                session that deferred its payloads sees it; prims inside an unloaded
                payload are then absent from every count.
        """
        return _profile_stage(stage_path, load_payloads)
