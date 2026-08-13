import pytest

BASE_USDA = """#usda 1.0

def Xform "World"
{
    def Sphere "Ball"
    {
        double radius = 1
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
