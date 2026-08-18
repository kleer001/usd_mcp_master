#!/usr/bin/env python
"""Command-line entry point. The same explainers, without an MCP client in the way.

Every module under this one already imports nothing from `mcp`, so this is a second
front door rather than a second implementation: `usd-explain` and `usd-mcp` call the
same functions and answer identically. What differs is who is asking — a person at a
terminal, a shell script, a CI job — and that they get JSON on stdout instead of a
tool result.

The binary name supplies the verb, so the commands drop it: `explain_value` is
`usd-explain value`, `explain_edit_target` is `usd-explain edit-target`. SPEC.md maps
the two vocabularies.

Writing is opt-in here on the same terms as in the server: without `--enable-write` the
three mutating commands are not registered, so `usd-explain set-attribute` is an
unrecognised command rather than a refused one. The dry run stays the default —
`--confirm` is what writes.

Results are bounded by default, on the same budgets the server uses, and `--full` turns
that off. Stdout reaches a pipe, a terminal, and an agent's shell tool alike, and two of
those three are hurt by a fifteen-megabyte mesh attribute — an agent driving this through
a shell is spending it against a context window exactly as an MCP client would. The
failure modes are not symmetric either: a script that forgets `--full` gets a result that
says `_truncated` and carries exact counts, while an agent that needed a bound and did not
get one has already lost the conversation. So the safe side is the default, and the caller
that genuinely wants every element of a mesh asks for it once.

This module parses arguments and prints results. It holds no USD logic.
"""

import argparse
import json
import sys

from usd_mcp import common
from usd_mcp.compose import explain_edit_target, explain_prim, explain_variants
from usd_mcp.diff import SCOPES, diff_stages
from usd_mcp.explain import explain_value, why_not_visible
from usd_mcp.portability import TARGETS, check_portability
from usd_mcp.profile import profile_stage
from usd_mcp.resolve import resolve_path
from usd_mcp.write import set_active, set_attribute, set_visibility

STAGE_HELP = "path to a .usd/.usda/.usdc/.usdz file"
PRIM_HELP = "absolute prim path, e.g. /World/Set/Chair"
LAYER_HELP = (
    "the layer to author into. Never inferred: guessing the edit target is the failure "
    "this tool exists to diagnose. Must be in the stage's root layer stack."
)
PAYLOAD_HELP = (
    "compose without payload contents, as a session that deferred them sees it. "
    "Answering with payloads loaded about a session without them reports a prim as "
    "visible while the artist is looking at nothing."
)
CONFIRM_HELP = (
    "author the edit. Without this nothing is written and the diff is printed instead: "
    "the layer the edit would land in, what would outrank it, and what the resolved "
    "value would become."
)


def _stage(parser):
    parser.add_argument("stage_path", metavar="STAGE", help=STAGE_HELP)


def _stage_prim(parser):
    _stage(parser)
    parser.add_argument("prim_path", metavar="PRIM", help=PRIM_HELP)


def _target_layer(parser):
    parser.add_argument("target_layer", metavar="LAYER", help=LAYER_HELP)


def _confirm(parser):
    parser.add_argument("--confirm", action="store_true", help=CONFIRM_HELP)


def _json_value(text):
    """An attribute value, given as JSON so its type is stated rather than guessed.

    `5` is a number and `"5"` is a string; a CLI that inferred the difference would
    author the wrong type into a stage and report success.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(
            f"not JSON: {text!r} ({error}). Numbers are bare, strings are quoted "
            f'(shell: \'"red"\'), vectors are arrays ([1, 0, 0]).'
        ) from error


def _add_read_commands(subparsers):
    value = subparsers.add_parser(
        "value", help="why an attribute resolves to the value it does"
    )
    _stage_prim(value)
    value.add_argument(
        "attribute_name", metavar="ATTR", help="e.g. radius, or primvars:displayColor"
    )
    value.add_argument(
        "--time-code", type=float, help="sample a frame; omit for the default time code"
    )
    value.set_defaults(
        run=lambda a: explain_value(a.stage_path, a.prim_path, a.attribute_name, a.time_code)
    )

    hidden = subparsers.add_parser(
        "why-not-visible",
        help="why a prim does not appear: missing, deactivated, unloaded, invisible, or purpose",
    )
    _stage_prim(hidden)
    hidden.add_argument("--no-payloads", action="store_true", help=PAYLOAD_HELP)
    hidden.set_defaults(
        run=lambda a: why_not_visible(a.stage_path, a.prim_path, not a.no_payloads)
    )

    prim = subparsers.add_parser("prim", help="the composition arcs that built a prim")
    _stage_prim(prim)
    prim.set_defaults(run=lambda a: explain_prim(a.stage_path, a.prim_path))

    variants = subparsers.add_parser(
        "variants", help="which variant is selected on a prim, and which layer selected it"
    )
    _stage_prim(variants)
    variants.set_defaults(run=lambda a: explain_variants(a.stage_path, a.prim_path))

    target = subparsers.add_parser(
        "edit-target", help="whether an edit authored in a layer would win or silently lose"
    )
    _stage_prim(target)
    target.add_argument("attribute_name", metavar="ATTR", help="e.g. radius")
    _target_layer(target)
    target.set_defaults(
        run=lambda a: explain_edit_target(
            a.stage_path, a.prim_path, a.attribute_name, a.target_layer
        )
    )

    resolve = subparsers.add_parser(
        "resolve", help="which file an asset path names, and against what it was anchored"
    )
    _stage(resolve)
    resolve.add_argument(
        "asset_path", metavar="ASSET", help="asset path as authored, e.g. ./tex/diffuse.exr"
    )
    resolve.add_argument(
        "--anchor-layer",
        help="resolve against this layer instead of the stage's root layer",
    )
    resolve.set_defaults(
        run=lambda a: resolve_path(a.stage_path, a.asset_path, a.anchor_layer)
    )

    diff = subparsers.add_parser(
        "diff", help="what changed between two stages, ignoring numbers within a tolerance"
    )
    diff.add_argument("stage_a", metavar="STAGE_A", help=STAGE_HELP)
    diff.add_argument("stage_b", metavar="STAGE_B", help=STAGE_HELP)
    diff.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help=(
            "absolute bound on every number compared. Zero, the default, is exact "
            "equality; a re-export's float noise sits around 1e-7."
        ),
    )
    diff.add_argument(
        "--scope",
        choices=SCOPES,
        default="composed",
        help=(
            "composed compares what the stages resolve to, sublayers and references "
            "included; layer compares one file each as authored."
        ),
    )
    diff.set_defaults(
        run=lambda a: diff_stages(a.stage_a, a.stage_b, a.tolerance, a.scope)
    )

    profile = subparsers.add_parser(
        "profile", help="where a stage's cost sits: layers, payloads, instancing, time"
    )
    _stage(profile)
    profile.add_argument("--no-payloads", action="store_true", help=PAYLOAD_HELP)
    profile.set_defaults(run=lambda a: profile_stage(a.stage_path, not a.no_payloads))

    portability = subparsers.add_parser(
        "portability", help="whether a destination host can read this stage's shading"
    )
    _stage(portability)
    portability.add_argument(
        "target",
        metavar="TARGET",
        choices=sorted(TARGETS),
        help="the destination host or render context",
    )
    portability.set_defaults(run=lambda a: check_portability(a.stage_path, a.target))


def _add_write_commands(subparsers):
    attribute = subparsers.add_parser(
        "set-attribute", help="author an attribute value into an explicit layer"
    )
    _stage_prim(attribute)
    attribute.add_argument("attribute_name", metavar="ATTR", help="e.g. radius")
    attribute.add_argument(
        "value", metavar="VALUE", type=_json_value, help="the value as JSON, matching the type"
    )
    _target_layer(attribute)
    _confirm(attribute)
    attribute.set_defaults(
        run=lambda a: set_attribute(
            a.stage_path, a.prim_path, a.attribute_name, a.value, a.target_layer, a.confirm
        )
    )

    visibility = subparsers.add_parser(
        "set-visibility", help="author visibility on a prim into an explicit layer"
    )
    _stage_prim(visibility)
    visibility.add_argument(
        "state",
        metavar="STATE",
        choices=("visible", "invisible"),
        help="visible authors `inherited`, which reveals nothing while an ancestor is invisible",
    )
    _target_layer(visibility)
    _confirm(visibility)
    visibility.set_defaults(
        run=lambda a: set_visibility(
            a.stage_path, a.prim_path, a.state == "visible", a.target_layer, a.confirm
        )
    )

    active = subparsers.add_parser(
        "set-active", help="author the active metadata on a prim into an explicit layer"
    )
    _stage_prim(active)
    active.add_argument(
        "state",
        metavar="STATE",
        choices=("active", "inactive"),
        help="inactive removes the prim's whole subtree from composition, not just its display",
    )
    _target_layer(active)
    _confirm(active)
    active.set_defaults(
        run=lambda a: set_active(
            a.stage_path, a.prim_path, a.state == "active", a.target_layer, a.confirm
        )
    )


def build_parser(enable_write=False):
    """Build the parser. Without `enable_write` it has no command that can author."""
    parser = argparse.ArgumentParser(
        prog="usd-explain",
        description=(
            "Explain OpenUSD composition: which layer won, why a prim is missing, where "
            "an edit would land. Reads local stages and prints JSON. Makes no network "
            "calls."
        ),
    )
    parser.add_argument(
        "--enable-write",
        action="store_true",
        help=(
            "register the mutating commands (set-attribute, set-visibility, set-active). "
            "Off by default: without it this tool has no write path at all."
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "report every list and array value whole, however large. Off by default: one "
            "mesh attribute in a published sample asset is 15 MB, which a pipe absorbs "
            "and a terminal or an agent's context window does not. Bounded results say "
            "so, and their counts are exact either way."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    _add_read_commands(subparsers)
    if enable_write:
        _add_write_commands(subparsers)
    return parser


# `--enable-write` decides which subparsers exist, so it has to be read before the real
# parser is built. This one knows that flag and ignores everything else.
_GATE = argparse.ArgumentParser(add_help=False)
_GATE.add_argument("--enable-write", action="store_true")


def main(argv=None):
    """Run one command and print its result. Returns the process exit status."""
    argv = sys.argv[1:] if argv is None else list(argv)
    gate, _ = _GATE.parse_known_args(argv)

    args = build_parser(enable_write=gate.enable_write).parse_args(argv)
    if args.full:
        common.unbound_results()
    try:
        result = args.run(args)
    except ValueError as error:
        print(f"usd-explain: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
