from refracto import grid
from refracto.declaration.model import Grid, Scenario


def _scn(level, module):
    return Scenario(id="x", grid=Grid(level, module), actor="a", precondition=[], inputs=[], intent="", steps=[])


def test_no_filter_selects_all():
    assert grid.select(_scn("smoke", "dataset"))


def test_level_filter():
    assert grid.select(_scn("smoke", "dataset"), level="smoke")
    assert not grid.select(_scn("regression", "dataset"), level="smoke")


def test_module_filter():
    assert grid.select(_scn("smoke", "dataset"), module="dataset")
    assert not grid.select(_scn("smoke", "etl"), module="dataset")


def test_both_filters_and():
    assert grid.select(_scn("smoke", "dataset"), level="smoke", module="dataset")
    assert not grid.select(_scn("smoke", "etl"), level="smoke", module="dataset")
