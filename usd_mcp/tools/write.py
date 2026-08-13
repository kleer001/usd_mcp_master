"""Mutating tools. Registered only when the server is started with `--enable-write`.

The `target_layer` and `confirm` guidance is spelled out in each docstring rather than
shared through a constant: a tool description is what the client actually reads before
calling, and an f-string is not a docstring at all.
"""

from typing import Any

from usd_mcp.write import set_active as _set_active
from usd_mcp.write import set_attribute as _set_attribute
from usd_mcp.write import set_visibility as _set_visibility


def register(server, annotations):
    @server.tool(annotations=annotations)
    def set_attribute(
        stage_path: str,
        prim_path: str,
        attribute_name: str,
        value: Any,
        target_layer: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Author an attribute value into an explicit layer.

        The attribute must already exist on the prim, by authored opinion or by schema;
        this overrides properties, it does not invent them.

        An edit into a layer that something stronger already overrides is applied where
        you asked and reported as not having moved the resolved value. Call
        explain_edit_target first if you still need to choose a layer.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
            attribute_name: attribute name, e.g. "radius".
            value: the value to author, matching the attribute's type.
            target_layer: the layer to author into. Required and never inferred —
                guessing the edit target is the failure this server exists to diagnose.
                Must be in the stage's root layer stack and outside any package.
            confirm: false, the default, writes nothing and returns the diff — the layer
                the edit would land in, what would outrank it, and what the resolved
                value would become. Show that to the user and call again with
                confirm=true only once they agree.
        """
        return _set_attribute(stage_path, prim_path, attribute_name, value, target_layer, confirm)

    @server.tool(annotations=annotations)
    def set_visibility(
        stage_path: str,
        prim_path: str,
        visible: bool,
        target_layer: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Author `visibility` on a prim into an explicit layer.

        Visibility inherits down namespace, so making a prim visible does not reveal it
        while an ancestor is invisible. The result reports the prim's computed
        visibility afterwards, so that case shows up rather than being assumed away.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
            visible: True authors `inherited`, False authors `invisible`.
            target_layer: the layer to author into. Required and never inferred. Must be
                in the stage's root layer stack and outside any package.
            confirm: false, the default, writes nothing and returns the diff. Show it to
                the user and call again with confirm=true only once they agree.
        """
        return _set_visibility(stage_path, prim_path, visible, target_layer, confirm)

    @server.tool(annotations=annotations)
    def set_active(
        stage_path: str,
        prim_path: str,
        active: bool,
        target_layer: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Author the `active` metadata on a prim into an explicit layer.

        Deactivating a prim removes its whole subtree from composition. Its descendants
        do not become hidden, they stop existing on the stage — a larger change than
        visibility, and rarely the one wanted for hiding something.

        Args:
            stage_path: path to a .usd/.usda/.usdc/.usdz file.
            prim_path: absolute prim path, e.g. /World/Set/Chair.
            active: False deactivates the prim and everything under it.
            target_layer: the layer to author into. Required and never inferred. Must be
                in the stage's root layer stack and outside any package.
            confirm: false, the default, writes nothing and returns the diff. Show it to
                the user and call again with confirm=true only once they agree.
        """
        return _set_active(stage_path, prim_path, active, target_layer, confirm)
