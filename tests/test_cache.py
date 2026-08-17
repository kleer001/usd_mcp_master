"""The stage cache: off by default, and never serving scene description that moved.

Composing a stage is nearly the whole cost of a tool call that reads one prim, so the
cache is worth having; a cached stage that has gone stale is a confident wrong answer,
so every test here is about the invalidation rather than about the speed.
"""

import os
from pathlib import Path

import pytest

from usd_mcp import common
from usd_mcp.common import open_stage
from usd_mcp.explain import explain_value


@pytest.fixture(autouse=True)
def cache_off_after_each_test():
    yield
    common._stage_cache = None
    common._cache_limit = 0


def touch(path, contents=None):
    """Rewrite a layer so its mtime moves, waiting out filesystem timestamp coarseness."""
    original = os.stat(path).st_mtime_ns
    if contents is not None:
        with open(path, "w", encoding="utf-8") as layer:
            layer.write(contents)
    while os.stat(path).st_mtime_ns == original:
        os.utime(path, ns=(original + 1_000_000, original + 1_000_000))


def edit_base_colour(tmp_path):
    """Change a value in the sublayer that the shot layer does not override."""
    base = str(tmp_path / "base.usda")
    touch(base, Path(base).read_text().replace("[(1, 0, 0)]", "[(0, 1, 0)]"))


def test_the_cache_is_off_until_asked_for(shot):
    assert open_stage(shot) is not open_stage(shot)


def test_an_unchanged_stage_is_served_from_memory(shot):
    common.enable_stage_cache()
    assert open_stage(shot) is open_stage(shot)


def test_the_load_state_is_part_of_the_key(composed):
    """A stage composed without payloads is a different stage, not the same one."""
    common.enable_stage_cache()
    assert open_stage(composed, load_payloads=True) is not open_stage(
        composed, load_payloads=False
    )


def test_editing_the_root_layer_invalidates(shot):
    common.enable_stage_cache()
    first = open_stage(shot)
    touch(shot)
    assert open_stage(shot) is not first


def test_editing_a_sublayer_invalidates(shot, tmp_path):
    """The root layer's mtime never moved; the composition changed anyway."""
    common.enable_stage_cache()
    first = open_stage(shot)
    edit_base_colour(tmp_path)

    assert open_stage(shot) is not first


def test_a_recomposed_stage_reads_the_edited_file(shot, tmp_path):
    """Invalidating is not enough on its own.

    USD will not re-read a layer it still holds, and a cached stage is what holds it, so
    a miss that kept any cached stage alive would recompose from the old scene
    description and report the old value with no error. Nothing here retains a stage,
    which is also true of a tool call.
    """
    common.enable_stage_cache()
    open_stage(shot)
    edit_base_colour(tmp_path)

    colour = explain_value(shot, "/World/Ball", "primvars:displayColor")
    assert colour["resolved_value"] == [[0.0, 1.0, 0.0]]


def test_deleting_a_layer_invalidates(composed, tmp_path):
    """A file that is gone fingerprints differently from a file that is there."""
    common.enable_stage_cache()
    first = open_stage(composed)
    os.remove(tmp_path / "payload.usda")
    assert open_stage(composed) is not first


def stages(tmp_path, count):
    """`count` distinct one-prim stages, so each takes its own cache key."""
    paths = []
    for index in range(count):
        path = tmp_path / f"stage{index}.usda"
        path.write_text(f'#usda 1.0\n\ndef Sphere "S{index}"\n{{\n}}\n')
        paths.append(str(path))
    return paths


def test_the_cache_is_bounded(tmp_path):
    """Least recently used goes first, so the bound holds however many are asked for."""
    common.enable_stage_cache(limit=2)
    a, b, c = stages(tmp_path, 3)

    open_stage(a)
    open_stage(b)
    assert len(common._stage_cache) == 2

    open_stage(c)
    assert len(common._stage_cache) == 2


def test_a_hit_refreshes_its_position(tmp_path):
    common.enable_stage_cache(limit=2)
    a, b, c = stages(tmp_path, 3)

    first = open_stage(a)
    open_stage(b)
    open_stage(a)  # a is now the most recently used, b the least
    open_stage(c)  # so c evicts b, not a

    assert open_stage(a) is first
    assert (os.path.realpath(b), True) not in common._stage_cache


def test_the_write_path_never_takes_a_cached_stage(shot):
    """An authored stage that fails to save holds an edit no fingerprint can see."""
    common.enable_stage_cache()
    read = open_stage(shot)
    assert open_stage(shot, cached=False) is not read
    assert open_stage(shot) is read
