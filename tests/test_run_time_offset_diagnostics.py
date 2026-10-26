"""Offset range errors describe the rejected range without exposing inputs."""
import copy

import pytest

from refracto.declaration import run_values
from refracto.declaration.loader import DeclarationError, _load_document
from refracto.declaration.model import RunTime
from tests.test_run_values_declaration import declaration


UNITS = [("days", 86400), ("hours", 3600), ("minutes", 60), ("seconds", 1)]
MAX_SECONDS = 315537897599


@pytest.fixture
def forbid_run_value_generation(monkeypatch):
    def forbidden():
        pytest.fail("declaration loading must not generate run values")
    monkeypatch.setattr(run_values, "_utc_now", forbidden)
    monkeypatch.setattr(run_values, "uuid4", forbidden)


@pytest.mark.parametrize("unit,factor", UNITS)
@pytest.mark.parametrize("sign", [-1, 1])
def test_out_of_range_time_offset_has_precise_value_free_diagnostic(
        unit, factor, sign, forbid_run_value_generation):
    amount = sign * (MAX_SECONDS // factor + 1)
    parameter_name = "private-offset-parameter-sentinel"
    raw = declaration({"name": "plain", parameter_name: {
        "from_run": "time", "offset": {unit: amount}}})
    before = copy.deepcopy(raw)
    with pytest.raises(DeclarationError) as error:
        _load_document(raw)
    assert str(error.value) == "time offset exceeds the representable datetime range"
    assert parameter_name not in str(error.value)
    assert str(amount) not in str(error.value)
    assert raw == before


@pytest.mark.parametrize("unit,factor", UNITS)
@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("below_limit", [0, 1])
def test_range_boundary_and_neighbor_remain_symbolic(
        unit, factor, sign, below_limit, forbid_run_value_generation):
    amount = sign * (MAX_SECONDS // factor - below_limit)
    raw = declaration({"name": {"from_run": "time", "offset": {unit: amount}}})
    before = copy.deepcopy(raw)
    scenario = _load_document(raw)
    assert scenario.parameters["name"] == RunTime(unit, amount)
    assert raw == before
    assert scenario.run_time is None
    assert scenario.run_time_values == {}
    assert not scenario.run_values_bound
