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


@pytest.fixture
def packaged(tmp_path):
    """A stage packaged into a .usdz.

    A packaged layer accepts an edit in memory and then refuses to save it, so it is
    the case where strength is the wrong question entirely.
    """
    source = tmp_path / "packaged_source.usda"
    source.write_text(BASE_USDA)
    usdz_path = tmp_path / "packaged.usdz"
    assert UsdUtils.CreateNewUsdzPackage(str(source), str(usdz_path))
    return str(usdz_path)
