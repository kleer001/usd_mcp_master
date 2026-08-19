import pytest
from pxr import UsdUtils

from usd_mcp import common


@pytest.fixture(autouse=True)
def process_wide_state_is_restored():
    """Put `common`'s module-level knobs back after every test.

    Both are deliberately process-wide — `unbound_results()` and `enable_stage_cache()`
    are called once by a front door at startup and never per call, which is what lets
    every `bounded()` read the budget rather than freeze it. That is safe in a process
    that answers one command and exits, and unsafe in a test session, where whichever
    test called them last decides what every later test sees.

    It had already bitten: `unbound_results()` nulls both budgets, the CLI's `--full`
    tests restored at most one of them through `monkeypatch`, and everything ordered
    after them ran with the bound switched off — so a bounding assertion there passed
    whether or not anything was bounding.
    """
    budgets = (common.MAX_FIELD_BYTES, common.MAX_VALUE_BYTES)
    cache, limit = common._stage_cache, common._cache_limit
    yield
    common.MAX_FIELD_BYTES, common.MAX_VALUE_BYTES = budgets
    common._stage_cache, common._cache_limit = cache, limit

BASE_USDA = """#usda 1.0

def Xform "World"
{
    def Sphere "Ball"
    {
        double radius = 1
        color3f[] primvars:displayColor = [(1, 0, 0)]
        matrix4d xformOp:transform = ( (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1) )
        token[] xformOpOrder = ["xformOp:transform"]
        asset texture = @./tex/diffuse.exr@
        asset missingTexture = @./tex/nosuchfile.exr@
    }

    def Xform "Hidden"
    {
        token visibility = "invisible"

        def Sphere "Inner"
        {
        }
    }

    def Xform "Off" (
        active = false
    )
    {
        def Sphere "Gone"
        {
        }
    }

    def Sphere "Guide"
    {
        token purpose = "guide"
    }

    def Material "Surface"
    {
    }
}
"""

SHOT_USDA = """#usda 1.0
(
    subLayers = [
        @./base.usda@
    ]
)

over "World"
{
    over "Ball"
    {
        double radius = 5
    }
}
"""


@pytest.fixture
def shot(tmp_path):
    """A two-layer stage: shot.usda sublayers base.usda and overrides one value."""
    (tmp_path / "base.usda").write_text(BASE_USDA)
    shot_path = tmp_path / "shot.usda"
    shot_path.write_text(SHOT_USDA)
    return str(shot_path)


PROP_USDA = """#usda 1.0

def Xform "Prop" (
    variantSets = "lod"
    variants = {
        string lod = "high"
    }
)
{
    variantSet "lod" = {
        "high" {
            double size = 10
        }
        "low" {
            double size = 2
        }
    }

    def Sphere "Geom"
    {
        double radius = 1
    }
}
"""

PAYLOAD_USDA = """#usda 1.0

def Sphere "Heavy"
{
    double radius = 100
}
"""

SET_USDA = """#usda 1.0

def Xform "Set"
{
    def "PropA" (
        references = @./prop.usda@</Prop>
    )
    {
    }

    def "PropB" (
        instanceable = true
        references = @./prop.usda@</Prop>
    )
    {
    }

    def "Deferred" (
        payload = @./payload.usda@</Heavy>
    )
    {
    }
}
"""

COMPOSED_SHOT_USDA = """#usda 1.0
(
    subLayers = [
        @./set.usda@
    ]
)

over "Set"
{
    over "PropA" (
        variants = {
            string lod = "low"
        }
    )
    {
    }
}
"""


@pytest.fixture
def composed(tmp_path):
    """A stage exercising every composition arc the explainers report.

    `/Set/PropA` references `prop.usda` and takes its `lod` selection from the shot
    layer, overriding the asset's own. `/Set/PropB` references the same asset but is
    `instanceable`, so its descendants are instance proxies. `/Set/Deferred` arrives
    through a payload.
    """
    (tmp_path / "prop.usda").write_text(PROP_USDA)
    (tmp_path / "payload.usda").write_text(PAYLOAD_USDA)
    (tmp_path / "set.usda").write_text(SET_USDA)
    shot_path = tmp_path / "shot.usda"
    shot_path.write_text(COMPOSED_SHOT_USDA)
    return str(shot_path)


PACKAGED_USDA = """#usda 1.0

def Xform "World"
{
    def Sphere "Ball"
    {
        double radius = 1
    }
}
"""


@pytest.fixture
def packaged(tmp_path):
    """A stage packaged into a .usdz.

    A packaged layer accepts an edit in memory and then refuses to save it, so it is
    the case where strength is the wrong question entirely. Its source carries no asset
    paths: packaging resolves and bundles them, which a fixture has no files for.
    """
    source = tmp_path / "packaged_source.usda"
    source.write_text(PACKAGED_USDA)
    usdz_path = tmp_path / "packaged.usdz"
    assert UsdUtils.CreateNewUsdzPackage(str(source), str(usdz_path))
    return str(usdz_path)


DRIFT_A_USDA = """#usda 1.0

def Xform "World"
{
    def Sphere "Ball"
    {
        double radius = 1
        color3f[] primvars:displayColor = [(1, 0, 0)]
        double spin.timeSamples = {
            1: 0,
            2: 10,
        }
    }

    def Sphere "Gone"
    {
        double radius = 2
    }

    def Sphere "Retyped"
    {
    }
}
"""

DRIFT_B_USDA = """#usda 1.0

def Xform "World"
{
    def Sphere "Ball"
    {
        double radius = 1.0000001
        color3f[] primvars:displayColor = [(0, 1, 0)]
        double spin.timeSamples = {
            1: 0,
            2: 10.0000001,
        }
    }

    def Cube "Retyped"
    {
    }

    def Sphere "Added"
    {
        double radius = 3
    }
}
"""


@pytest.fixture
def drifted(tmp_path):
    """Two single-layer stages differing by both float noise and real edits.

    `/World/Ball` carries a radius and an animated `spin` that moved by 1e-7 — the
    signature of a re-export — alongside a display colour that actually changed.
    `/World/Gone` is absent from the second, `/World/Added` is new, and
    `/World/Retyped` changed type. Single-layer so the composed and per-layer scopes
    have the same material to work on.
    """
    a = tmp_path / "drift_a.usda"
    b = tmp_path / "drift_b.usda"
    a.write_text(DRIFT_A_USDA)
    b.write_text(DRIFT_B_USDA)
    return str(a), str(b)


PROFILE_ASSET_USDA = """#usda 1.0

def Xform "Prop"
{
    def Sphere "Geom"
    {
        double radius.timeSamples = {
            1: 1,
            2: 2,
        }
        asset texture.timeSamples = {
            1: @./tex.exr@,
            2: @./tex.exr@,
        }
    }
}
"""

PROFILE_SHOT_USDA = """#usda 1.0

def Xform "Set"
{
    def "PropA" (
        instanceable = true
        references = @./asset.usda@</Prop>
    )
    {
    }

    def "Deferred" (
        payload = @./asset.usda@</Prop>
    )
    {
    }
}
"""


@pytest.fixture
def profiled(tmp_path):
    """A stage carrying every cost the profiler names.

    `/Set/PropA` is instanceable, so its geometry is an instance proxy; `/Set/Deferred`
    arrives through a payload. Both reach an asset whose `radius` is genuinely animated
    and whose `texture` is authored once per frame at the same value — animation that
    makes the stage time-dependent and changes nothing. No frame range is authored.
    """
    (tmp_path / "asset.usda").write_text(PROFILE_ASSET_USDA)
    shot_path = tmp_path / "shot.usda"
    shot_path.write_text(PROFILE_SHOT_USDA)
    return str(shot_path)


LOOKS_USDA = """#usda 1.0

def Scope "Looks"
{
    def Material "Portable"
    {
        token outputs:surface.connect = </Looks/Portable/Surface.outputs:surface>
        token outputs:displacement

        def Shader "Surface"
        {
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor.connect = </Looks/Portable/Texture.outputs:rgb>
            color3f inputs:specularColor.connect = </Looks/Portable/Texture.outputs:rgb>
            token outputs:surface
        }

        def Shader "Texture"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @./tex.exr@
            float3 outputs:rgb
        }
    }

    def Material "Both"
    {
        token outputs:surface.connect = </Looks/Both/Preview.outputs:surface>
        token outputs:ri:surface.connect = </Looks/Both/Pxr.outputs:surface>

        def Shader "Preview"
        {
            uniform token info:id = "UsdPreviewSurface"
            token outputs:surface
        }

        def Shader "Pxr"
        {
            uniform token info:id = "PxrSurface"
            token outputs:surface
        }
    }

    def Material "RiOnly"
    {
        token outputs:ri:surface.connect = </Looks/RiOnly/Pxr.outputs:surface>

        def Shader "Pxr"
        {
            uniform token info:id = "PxrSurface"
            token outputs:surface
        }
    }

    def Material "Mislabelled"
    {
        token outputs:surface.connect = </Looks/Mislabelled/Pxr.outputs:surface>

        def Shader "Pxr"
        {
            uniform token info:id = "PxrSurface"
            token outputs:surface
        }
    }

    def Material "Empty"
    {
    }
}
"""


@pytest.fixture
def looks(tmp_path):
    """Five materials covering every way a handoff survives or fails.

    `Portable` provides only the universal `UsdPreviewSurface` network, reusing one
    texture across two inputs and declaring a displacement output it never connects. `Both` provides
    that and a RenderMan one. `RiOnly` provides RenderMan and nothing else. `Mislabelled`
    wires a renderer's own shader to the universal output, promising a portability it
    does not have. `Empty` authors no terminal at all.
    """
    stage_path = tmp_path / "looks.usda"
    stage_path.write_text(LOOKS_USDA)
    return str(stage_path)


WIDE_LAYERS = 60


def _wide_layer(index, variant):
    """One sublayer of the `wide` fixture, authoring a slice of every bounded list.

    `Contested` collects an opinion per layer, so its property stack outruns the bound
    on its own. The rest give the diff more added, removed, retyped, and changed prims
    than it is allowed to itemise.
    """
    only = "gone" if variant == "a" else "new"
    shifted = "Sphere" if variant == "a" else "Cube"
    kept = index if variant == "a" else index + 100
    return f"""#usda 1.0

over "World"
{{
    over "Contested"
    {{
        double size = {index}
    }}

    def Xform "keep{index:03d}"
    {{
        double size = {kept}
    }}

    def {shifted} "shifted{index:03d}"
    {{
    }}

    def Sphere "{only}{index:03d}"
    {{
    }}
}}
"""


def _wide_root(variant, sublayers):
    materials = "\n\n".join(
        f'    def Material "Mat{i:03d}"\n    {{\n    }}' for i in range(WIDE_LAYERS)
    )
    paths = ",\n        ".join(f"@./{name}@" for name in sublayers)
    return f"""#usda 1.0
(
    subLayers = [
        {paths}
    ]
)

def Xform "World"
{{
    def Xform "Contested"
    {{
    }}

{materials}
}}
"""


@pytest.fixture
def wide(tmp_path):
    """A stage pair that overruns the result bound in every list the bound applies to.

    Sixty sublayers per stage, so the layer stack and the per-layer profile both exceed
    the budget; one attribute carrying an opinion in every one of them, so the property
    stack does too; sixty materials, so the portability report does; and a second stage
    that changes, adds, removes, and retypes a prim per layer, so no list in a diff is
    short enough to escape the bound.

    Deliberately larger than the bound and no larger. The measured case that motivates
    it — a 200-layer, 10,000-prim stage returning 1.59 MB — is too slow to build per
    test, and the bound either holds at 60 or it does not hold at all.
    """
    stages = {}
    for variant in ("a", "b"):
        names = []
        for index in range(WIDE_LAYERS):
            name = f"wide_{variant}_{index:03d}.usda"
            (tmp_path / name).write_text(_wide_layer(index, variant))
            names.append(name)
        root = tmp_path / f"wide_{variant}.usda"
        root.write_text(_wide_root(variant, names))
        stages[variant] = str(root)
    return stages["a"], stages["b"]


ARRAY_POINTS = 200
VARIANT_COUNT = 60


@pytest.fixture
def bulky(tmp_path):
    """A stage whose size lives in one attribute value and one variant set.

    Neither is a long *list of results* — they are a single authored value and a single
    prim's variants — so the result-list bound does not reach them and they need their
    own. The mesh carries an array longer than the bound; `Switch` offers more variants
    than the bound; and `points` differs between the two stages only at its **last**
    element, which is what a diff must still catch after the reported value is trimmed.
    """
    from pxr import Gf, Usd, UsdGeom, Vt

    def build(name, tweak_last):
        path = tmp_path / name
        stage = Usd.Stage.CreateNew(str(path))
        mesh = UsdGeom.Mesh.Define(stage, "/Mesh")
        points = [Gf.Vec3f(i, i, i) for i in range(ARRAY_POINTS)]
        if tweak_last:
            points[-1] = Gf.Vec3f(-1, -2, -3)
        mesh.GetPointsAttr().Set(Vt.Vec3fArray(points))

        switch = stage.DefinePrim("/Switch", "Xform")
        variants = switch.GetVariantSets().AddVariantSet("take")
        for index in range(VARIANT_COUNT):
            variants.AddVariant(f"take{index:03d}")
        variants.SetVariantSelection("take000")
        stage.GetRootLayer().Save()
        return str(path)

    return build("bulky_a.usda", False), build("bulky_b.usda", True)
