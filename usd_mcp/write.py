"""The write path. The only module in the package that authors scene description.

Every other module reads. Confining authoring to one file is what lets the safety
contract stay checkable: `tests/test_safety_contract.py` allows USD authoring calls
here and nowhere else, so "which code can change my stage" has a one-file answer a
reviewer can read in a sitting.

Three rules hold for every function here, and each is a defect if it stops holding:

1. **The edit target is given, never inferred.** Guessing which layer an edit belongs
   in is the failure the rest of this package exists to diagnose.
2. **Nothing is written until `confirm=True`.** The default call reports what the
   edit would do and touches nothing, so a caller gets the diff without asking for
   it. A caller that passes `confirm=True` on its first call writes immediately —
   the default is a diff, not a gate, and nothing here enforces a second call.
3. **Every applied mutation is appended to the audit log** before the call returns.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pxr import Tf, Usd, UsdGeom

from usd_mcp.common import (
    bounded_value,
    open_stage,
    plain,
    require_attribute,
    require_prim,
    root_layer_stack,
    value_brief,
)
from usd_mcp.compose import edit_target_verdict, layer_in_root_stack

AUDIT_LOG_ENV = "USD_MCP_AUDIT_LOG"
DEFAULT_AUDIT_LOG = Path.home() / ".usd-mcp" / "audit.log"


def set_attribute(stage_path, prim_path, attribute_name, value, target_layer, confirm=False):
    """Author an attribute value into an explicit layer.

    The attribute must already exist on the prim, by authored opinion or by schema.
    Inventing a property the schema does not define is a different operation with
    different consequences, and is not this one.
    """
    stage = open_stage(stage_path, cached=False)
    prim = require_prim(stage, prim_path)
    _require_authorable(prim)
    attr = require_attribute(prim, attribute_name)
    layer = _writable_layer(stage, target_layer)
    verdict = edit_target_verdict(prim, attr, layer)

    prior = plain(attr.Get())
    plan = _plan("attribute", attribute_name, prior, value, layer, verdict, confirm)
    if not confirm:
        return plan

    with Usd.EditContext(stage, Usd.EditTarget(layer)):
        _author(lambda: attr.Set(value), attribute_name, value)
    _save(layer)

    return _applied(plan, stage_path, prim, layer, attribute_name, prior, plain(attr.Get()))


def set_visibility(stage_path, prim_path, visible, target_layer, confirm=False):
    """Author `visibility` on a prim into an explicit layer.

    Visibility inherits down namespace, so making a prim visible does not reveal it
    when an ancestor is invisible. The resolved value reported afterwards is the
    prim's computed visibility, not the token authored, precisely so that case shows.
    """
    stage = open_stage(stage_path, cached=False)
    prim = require_prim(stage, prim_path)
    _require_authorable(prim)
    imageable = UsdGeom.Imageable(prim)
    if not imageable:
        raise ValueError(
            f"{prim_path} is type {prim.GetTypeName() or '<untyped>'}, not an Imageable; "
            f"it has no visibility to author."
        )

    layer = _writable_layer(stage, target_layer)
    attr = imageable.GetVisibilityAttr()
    verdict = edit_target_verdict(prim, attr, layer)

    token = UsdGeom.Tokens.inherited if visible else UsdGeom.Tokens.invisible
    prior = str(imageable.ComputeVisibility())
    plan = _plan("attribute", "visibility", prior, str(token), layer, verdict, confirm)
    if not confirm:
        return plan

    with Usd.EditContext(stage, Usd.EditTarget(layer)):
        _author(lambda: attr.Set(token), "visibility", token)
    _save(layer)

    computed = str(UsdGeom.Imageable(prim).ComputeVisibility())
    result = _applied(plan, stage_path, prim, layer, "visibility", prior, computed)
    if visible and computed == str(UsdGeom.Tokens.invisible):
        result["explanation"] += (
            " The prim is still computed invisible: visibility inherits, so an ancestor "
            "authoring `invisible` overrides this. Call why_not_visible to name it."
        )
    return result


def set_active(stage_path, prim_path, active, target_layer, confirm=False):
    """Author the `active` metadata on a prim into an explicit layer.

    Deactivating a prim removes its entire subtree from composition — descendants are
    not merely hidden, they stop existing on the stage.
    """
    stage = open_stage(stage_path, cached=False)
    prim = require_prim(stage, prim_path)
    _require_authorable(prim)
    layer = _writable_layer(stage, target_layer)

    prior = prim.IsActive()
    verdict = _metadata_verdict(stage, prim, layer, "active")
    plan = _plan("metadata", "active", prior, active, layer, verdict, confirm)
    if not confirm:
        return plan

    with Usd.EditContext(stage, Usd.EditTarget(layer)):
        _author(lambda: prim.SetActive(active), "active", active)
    _save(layer)

    # A deactivated prim stays addressable; its descendants do not compose at all.
    return _applied(plan, stage_path, prim, layer, "active", prior, prim.IsActive())


def _plan(kind, name, prior, new, layer, verdict, confirm):
    """The diff both a dry run and an applied edit report, before anything is written."""
    return {
        "applied": False,
        "confirmed": confirm,
        "target_layer": layer.identifier,
        "change": {
            "kind": kind,
            "name": name,
            "from": bounded_value(prior),
            "to": bounded_value(plain(new)),
        },
        "would_win": verdict["would_win"],
        "blocked_by": verdict["blocked_by"],
        "outranked_by": verdict["outranked_by"],
        "resolved_value_after": None,
        "explanation": _plan_explanation(verdict, confirm),
        "audit_log": None,
    }


def _plan_explanation(verdict, confirm):
    if confirm:
        return verdict["explanation"]
    return (
        f"Dry run — nothing was written. {verdict['explanation']} "
        f"Call again with confirm=true to author it."
    )


def _applied(plan, stage_path, prim, layer, name, prior, after):
    """The applied result, and the audit entry that must survive it.

    The result is bounded; the audit log is not. A record of what was authored is worth
    nothing if it records only the leading elements of what was authored.
    """
    plan = dict(plan)
    plan["applied"] = True
    plan["resolved_value_after"] = bounded_value(after)
    if plan["blocked_by"] == "strength":
        plan["explanation"] = (
            f"Authored into {layer.identifier}, and the resolved value did not change: "
            f"{plan['outranked_by']['layer']} authors "
            f"{value_brief(plan['outranked_by']['value'])} and is stronger. The opinion is now "
            f"in the layer you asked for, outranked where it sits."
        )
    else:
        plan["explanation"] = (
            f"Authored into {layer.identifier}. {name} is now {value_brief(after)}."
        )
    plan["audit_log"] = _audit(
        stage_path, str(prim.GetPath()), layer.identifier, name, prior, after
    )
    return plan


def _metadata_verdict(stage, prim, layer, field):
    """The strength verdict for prim metadata, which has no `UsdAttributeQuery`.

    Only a layer in the root layer stack may be a target, and for a given prim a local
    opinion outranks anything arriving through a reference, so position in the root
    layer stack settles it.
    """
    order = {candidate.identifier: i for i, candidate in enumerate(root_layer_stack(stage))}
    target_strength = order.get(layer.identifier)
    blocker = None
    for spec in prim.GetPrimStack():
        strength = order.get(spec.layer.identifier)
        if strength is None or strength >= target_strength or not spec.HasInfo(field):
            continue
        blocker = {
            "layer": spec.layer.identifier,
            "value": bounded_value(plain(spec.GetInfo(field))),
        }
        break

    return {
        "would_win": blocker is None,
        "blocked_by": "strength" if blocker else None,
        "target_writable": True,
        "outranked_by": blocker,
        "value_that_would_survive": blocker["value"] if blocker else None,
        "explanation": (
            f"An opinion authored in {layer.identifier} would win: no stronger layer authors "
            f"`{field}`."
            if blocker is None
            else f"An opinion authored in {layer.identifier} would lose: {blocker['layer']} "
            f"authors `{field}` = {value_brief(blocker['value'])} and is stronger."
        ),
    }


def _require_authorable(prim):
    """Refuse a prim that cannot hold an opinion no matter which layer is targeted."""
    if prim.IsInstanceProxy():
        raise ValueError(
            f"{prim.GetPath()} is an instance proxy: it exists only through an ancestor "
            f"marked `instanceable`, and an opinion authored at this path is discarded "
            f"whatever layer it goes in. Author on the corresponding prim in the "
            f"prototype's source, or clear `instanceable` on the ancestor."
        )


def _writable_layer(stage, target_layer):
    """The target layer, or a refusal naming why it cannot hold an edit."""
    layer = layer_in_root_stack(stage, target_layer)
    if layer.GetFileFormat().IsPackage() or not layer.permissionToEdit:
        raise ValueError(
            f"{layer.identifier} cannot be authored into. A packaged layer accepts an edit in "
            f"memory and then refuses to save it. Pick a layer outside the package."
        )
    return layer


def _author(action, name, value):
    """Run one authoring call, translating USD's exception into the documented one."""
    try:
        if action() is False:
            raise ValueError(f"USD refused to author {name} = {value!r}")
    except Tf.ErrorException as error:
        raise ValueError(f"could not author {name} = {value!r}: {error}") from error


def _save(layer):
    try:
        layer.Save()
    except Tf.ErrorException as error:
        raise ValueError(f"could not save {layer.identifier}: {error}") from error


def audit_log_path():
    """Where applied mutations are recorded; `USD_MCP_AUDIT_LOG` overrides the default."""
    return Path(os.environ.get(AUDIT_LOG_ENV) or DEFAULT_AUDIT_LOG)


def _audit(stage_path, prim_path, layer, name, prior, after):
    """Append one applied mutation to the audit log and return the log's path.

    Appended before the call returns, so a mutation that reached the stage cannot be
    absent from the record.
    """
    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage_path,
        "layer": layer,
        "prim": prim_path,
        "name": name,
        "from": prior,
        "to": after,
    }
    with open(path, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")
    return str(path)
