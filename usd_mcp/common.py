"""Boundary helpers shared by the explainers.

Opening a stage, demanding a prim, and converting USD's C++ types to Python ones
are the three things every explainer does before it can say anything. They live
here so both explainer modules convert at the same boundary rather than each
growing its own.
"""

from pxr import Tf, Usd


def open_stage(stage_path):
    """Open a stage, or raise `ValueError` naming what went wrong.

    Every way of failing to open a stage — missing file, wrong format, malformed
    scene description — surfaces from USD as `Tf.ErrorException`, which carries the
    parse error but not a type any caller here would think to catch. Translating it
    at this boundary is what makes the `ValueError` contract the rest of the package
    documents actually hold.
    """
    try:
        stage = Usd.Stage.Open(stage_path)
    except Tf.ErrorException as error:
        raise ValueError(f"could not open as a USD stage: {stage_path}: {error}") from error
    if not stage:
        raise ValueError(f"could not open as a USD stage: {stage_path}")
    return stage


def require_prim(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"no prim at {prim_path}")
    return prim


def require_attribute(prim, attribute_name):
    attr = prim.GetAttribute(attribute_name)
    if not attr:
        raise ValueError(f"{prim.GetPath()} has no attribute {attribute_name!r}")
    return attr


def root_layer_stack(stage):
    """The stage's layer stack, strongest first, without the session layer.

    A stage always carries an anonymous session layer that nobody authored and
    nobody can open. Reporting it as part of the layer stack invites an edit
    aimed at a layer that will not survive the session.
    """
    return stage.GetLayerStack(includeSessionLayers=False)


def plain(value):
    """USD values are C++ types; JSON needs Python ones."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "__len__") and not isinstance(value, str):
        return [plain(item) for item in value]
    return str(value)
