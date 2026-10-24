"""UTC time declarations remain bounded, symbolic and deterministic."""
import copy
from datetime import datetime, timedelta, timezone
import json

import pytest

from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document
from refracto.declaration.run_values import bind_run_values
from tests.test_run_values_declaration import declaration


BASE = "2026-10-24T08:00:00.123Z"


def case(marker=None):
    return declaration({"name": marker if marker is not None else {"from_run": "time"}})


def test_fixed_time_is_a_symbolic_parameter_until_explicit_binding():
    original = _load_document(case({"from_run": "time", "offset": {"days": 7}}))
    before = copy.deepcopy(original)
    view = expansion_view(original)
    assert view["parameters"]["name"] == {
        "kind": "run-value", "from_run": "time", "offset": {"days": 7}}
    bound, token = bind_run_values(original, run_time=BASE)
    assert token is None
    assert bound.parameters["name"] == "2026-10-31T08:00:00.123Z"
    assert bound.run_time == BASE and bound.run_time_source == "fixed"
    assert bound.run_time_values == {"name": "2026-10-31T08:00:00.123Z"}
    assert original == before
    step, _ = prepare_step(bound.steps[0], bound, {})
    assert step.request.body["name"] == "2026-10-31T08:00:00.123Z"
    with pytest.raises(ValueError, match="symbolic"):
        expansion_view(bound)


@pytest.mark.parametrize("unit,factor", [("days", 86400), ("hours", 3600), ("minutes", 60), ("seconds", 1)])
@pytest.mark.parametrize("amount", [-7, 0, 7])
def test_supported_units_and_signs_are_exact_fixed_durations(unit, factor, amount):
    bound, _ = bind_run_values(_load_document(case({"from_run": "time", "offset": {unit: amount}})),
                              run_time=BASE)
    expected = datetime(2026, 10, 24, 8, 0, 0, 123000, timezone.utc) + timedelta(seconds=factor * amount)
    assert bound.parameters["name"] == expected.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@pytest.mark.parametrize("marker", [
    {"from_run": "time", "offset": {}}, {"from_run": "time", "offset": None},
    {"from_run": "time", "offset": []}, {"from_run": "time", "offset": "7 days"},
    {"from_run": "time", "offset": {"days": 7, "hours": 1}},
    {"from_run": "time", "offset": {"months": 1}},
    {"from_run": "time", "offset": {"years": 1}},
    {"from_run": "time", "offset": {"days": True}},
    {"from_run": "time", "offset": {"days": False}},
    {"from_run": "time", "offset": {"days": 1.0}},
    {"from_run": "time", "offset": {"days": "1"}},
    {"from_run": "time", "offset": {"days": None}},
    {"from_run": "time", "offset": {"days": {"from_parameter": "n"}}},
    {"from_run": "time", "offset": {"days": []}},
    {"from_run": "time", "offset": {"seconds": 315537897600}},
    {"from_run": "time", "offset": {"seconds": -315537897600}},
    {"from_run": "time", "timezone": "UTC"},
    {"from_run": "time", "format": "date"},
    {"from_run": "time", "prefix": "x"},
    {"from_run": "time", "concat": ["x"]},
    {"from_run": "unique", "offset": {"days": 1}},
    {"from_run": "Time"}, {"from_run": "now"},
])
def test_invalid_time_forms_fail_before_binding(marker):
    with pytest.raises(DeclarationError):
        _load_document(case(marker))


@pytest.mark.parametrize("position", ["body", "path", "query", "headers", "assertion", "concat"])
def test_time_markers_are_not_a_step_level_expression(position):
    raw = declaration({"name": "plain"})
    action = raw["steps"][0]["do"]["request"]
    marker = {"from_run": "time"}
    if position == "path":
        action["path"].append(marker)
    elif position == "assertion":
        raw["steps"][0]["expect"]["response"].append({"check": "field_equals", "field": "time", "value": marker})
    elif position == "concat":
        action["body"]["name"] = {"concat": [marker]}
    else:
        action[position] = {"name": marker}
    with pytest.raises(DeclarationError):
        _load_document(raw)


@pytest.mark.parametrize("value", [
    "2026-10-24T08:00:00Z", "2026-10-24T08:00:00.123456Z",
    "2026-10-24T08:00:00.123+00:00", "2026-10-24T08:00:00.123z",
    "2026-10-24 08:00:00.123Z", "2026-10-24T08:00:00.123Z\n",
    "2026-02-29T00:00:00.000Z", "2026-10-24T24:00:00.000Z",
    "2026-10-24T08:00:60.000Z", "0000-01-01T00:00:00.000Z",
    "10000-01-01T00:00:00.000Z", "２０２６-10-24T08:00:00.123Z",
    "sensitive-invalid-time", True, 0, 1.5, {}, [],
    datetime(2026, 10, 24, tzinfo=timezone.utc),
])
def test_fixed_time_requires_exact_canonical_string_without_leaking_input(value):
    with pytest.raises(ValueError) as error:
        bind_run_values(_load_document(case()), run_time=value)
    assert str(error.value) == "run_time must be a valid UTC timestamp in YYYY-MM-DDTHH:MM:SS.sssZ format"


@pytest.mark.parametrize("base,offset,expected", [
    ("0001-01-01T00:00:00.000Z", 0, "0001-01-01T00:00:00.000Z"),
    ("9999-12-31T23:59:59.999Z", 0, "9999-12-31T23:59:59.999Z"),
    ("0001-01-01T00:00:00.000Z", 315537897599, "9999-12-31T23:59:59.000Z"),
    ("9999-12-31T23:59:59.999Z", -315537897599, "0001-01-01T00:00:00.999Z"),
    ("2028-02-28T12:00:00.000Z", 86400, "2028-02-29T12:00:00.000Z"),
])
def test_calendar_boundaries_and_leap_day_are_valid(base, offset, expected):
    bound, _ = bind_run_values(_load_document(case({"from_run": "time", "offset": {"seconds": offset}})),
                              run_time=base)
    assert bound.parameters["name"] == expected


@pytest.mark.parametrize("base,offset", [("0001-01-01T00:00:00.000Z", -1), ("9999-12-31T23:59:59.999Z", 1)])
def test_selected_base_overflow_cannot_wrap_or_fall_back(base, offset):
    original = _load_document(case({"from_run": "time", "offset": {"seconds": offset}}))
    before = copy.deepcopy(original)
    with pytest.raises(ValueError, match="overflows"):
        bind_run_values(original, run_time=base)
    assert original == before and original.run_time is None and not original.run_time_values


def test_nested_marker_looking_data_is_not_a_clock_request(monkeypatch):
    from refracto.declaration import run_values
    monkeypatch.setattr(run_values, "_utc_now", lambda: pytest.fail("literal data read clock"))
    payload = {"nested": {"from_run": "time", "offset": {"days": "data"}},
               "items": [{"from_run": "time"}]}
    bound, _ = bind_run_values(_load_document(case(payload)))
    assert bound.parameters["name"] == payload and bound.run_time is None
    assert prepare_step(bound.steps[0], bound, {})[0].request.body == {"name": payload}


def test_time_and_concat_keep_distinct_metadata_and_parameter_scope():
    original = _load_document(declaration({
        "name": {"concat": ["at-", {"from_parameter": "time"}, "-end"]},
        "time": {"from_run": "time"}}))
    bound, _ = bind_run_values(original, run_time=BASE)
    assert bound.parameters["name"] == f"at-{BASE}-end"
    assert bound.run_time_values == {"time": BASE}
    assert BASE not in repr(bound)
    assert "run-value" in json.dumps(expansion_view(original))


def test_numeric_assertion_does_not_gain_timestamp_ordering():
    raw = case()
    raw["steps"][0]["expect"]["response"] = [{
        "check": "field_compare", "field": "time", "op": ">=", "value": {"from_parameter": "name"}}]
    with pytest.raises(DeclarationError):
        _load_document(raw)
