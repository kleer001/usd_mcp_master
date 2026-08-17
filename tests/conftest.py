import pytest
from pxr import UsdUtils

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
