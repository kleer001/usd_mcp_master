"""Named diagnostic sequences.

The tools each answer one question. These name the order to ask them in for the
two investigations that take more than one question, so the sequence is offered
rather than reconstructed each time.
"""


def _fix_step_text(enable_write):
    """What to do once the layer is known, which depends on the server having a write path.

    A prompt naming tools the server did not register would send a client after
    something that does not exist, so the read-only build stops at the diagnosis.
    """
    if not enable_write:
        return (
            " This server is read-only, so report the layer and the value to author and "
            "stop there; do not claim the fix has been made."
        )
    return (
        " Then author it: call set_attribute with that layer as target_layer and leave "
        "confirm at false, show the user the diff it returns, and call again with "
        "confirm=true only once they agree."
    )


def register(server, enable_write=False):
    @server.prompt()
    def debug_override(stage_path: str, prim_path: str, attribute_name: str) -> str:
        """Work out why an override is not changing the resolved value.

        Args:
            stage_path: path to the stage the override was authored into.
            prim_path: absolute path of the prim being overridden.
            attribute_name: the attribute that is not changing.
        """
        return (
            f"An override on {attribute_name} at {prim_path} in {stage_path} is not taking "
            f"effect. Work through the causes in order of how often they are the answer, and "
            f"stop at the first that explains it:\n\n"
            f"1. Call explain_value for the attribute. If the override appears in "
            f"authored_opinions but does not win, the layer holding it is too weak — the "
            f"winning opinion names the layer that beat it.\n"
            f"2. If the override does not appear at all, it was authored somewhere that is "
            f"not in this stage's layer stack. Call explain_prim to see which arcs bring this "
            f"prim in, and check its instancing block: an opinion authored on an instance "
            f"proxy is discarded with no error.\n"
            f"3. If the attribute is driven by a variant, call explain_variants — a selection "
            f"authored in a weak layer loses the same way a value does.\n"
            f"4. Once the intended layer is known, call explain_edit_target for it to confirm "
            f"an opinion authored there would actually win.\n\n"
            f"Report the cause and the layer to author in. Do not propose an edit that "
            f"explain_edit_target says would lose." + _fix_step_text(enable_write)
        )

    @server.prompt()
    def audit_layer_stack(stage_path: str) -> str:
        """Review what a shot layer actually contributes before publishing it.

        Args:
            stage_path: path to the shot or shot-level stage to audit.
        """
        return (
            f"Audit {stage_path} before it is published.\n\n"
            f"1. Read the usd://stage/{stage_path}/summary and "
            f"usd://stage/{stage_path}/layer-stack resources to establish the root prims, "
            f"the frame range, and which layers compose in and in what order.\n"
            f"2. For each root prim, call explain_prim to record the arcs it arrives "
            f"through, and flag any prim marked instanceable whose descendants a downstream "
            f"department would expect to override.\n"
            f"3. For each prim carrying a variant set, call explain_variants and flag any "
            f"selection that is inherited from the asset rather than chosen in this stage — "
            f"those change under the shot when the asset is updated.\n"
            f"4. Call why_not_visible on every root prim and report any that does not render, "
            f"along with the layer responsible.\n\n"
            f"Report findings grouped by prim, naming the layer behind each one."
        )
