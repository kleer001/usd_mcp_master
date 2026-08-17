"""Stage comparison tool."""

from typing import Any

from usd_mcp.diff import diff_stages as _diff_stages


def register(server, annotations):
    @server.tool(annotations=annotations)
    def diff_stages(
        stage_a: str, stage_b: str, tolerance: float = 0.0, scope: str = "composed"
    ) -> dict[str, Any]:
        """Compare two stages: prims added, removed, retyped, and attributes changed.

        Unlike a text diff of the two files, numbers are compared against a tolerance, so
        the float noise of a re-export can be told apart from a real edit. Differences the
        tolerance absorbs are counted in counts.within_tolerance rather than dropped
        silently.

        Args:
            stage_a: path to the first .usd/.usda/.usdc/.usdz file.
            stage_b: path to the second file, compared against the first.
            tolerance: absolute bound applied to every number compared, including vector
                and matrix components, array elements, and time sample times. 0 is exact.
            scope: "composed" compares what the two stages resolve to, references,
                payloads, sublayers and variants included. "layer" compares only what the
                two files themselves author, which is the question after a re-export.
        """
        return _diff_stages(stage_a, stage_b, tolerance, scope)
