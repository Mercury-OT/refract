"""Regression checks for observed numeric types and unevaluated evidence."""
from pathlib import Path

import pytest
import yaml

from examples.minimal.adapters import build_adapters
from refracto import ports, runner
from refracto.declaration.loader import _load_document
from refracto.declaration.model import Assertion
from refracto.projection import backend, e2e
from refracto.query import parse_query
from tests.fakes import FakeApi, FakeNormalizer, FakeRecorder


def request_document(*, response=None, state=None, poll=None):
    step = {
        "id": "read",
        "do": {"request": {"method": "GET", "path": ["records"]}},
        "expect": {
            "response": response or [{"check": "success"}],
            "backend_state": state or [],
        },
    }
    if poll is not None:
        step["poll"] = {"on_timeout": poll}
    return {"schema_version": 1, "scenario": "evidence.edges", "users": [],
            "steps": [step]}


class Clock:
    def __init__(self):
        self.time = 0.0

    def now(self):
        return self.time

    def sleep(self, duration):
        self.time += duration


class ObservedState:
    def __init__(self, attributes):
        self.attributes = attributes
        self.calls = []

    def observe(self, trace):
        self.calls.append(trace)
        return ports.StateFacts(trace, [ports.Span("stored", self.attributes)])


def execute(projection, raw, state, *, response=None):
    clock = Clock()
    api = FakeApi({("GET", "records"): {
        "status": 200, "json": {"success": True, "data": response or {}}}})
    options = dict(
        auth=None, api=api, state=state, recorder=FakeRecorder(),
        normalizer=FakeNormalizer(),
        resolve_request=lambda scenario, step, template: ports.RequestSpec(
            template.method, template.path, template.body),
        now=clock.now, sleep=clock.sleep,
        poll_config=runner.PollConfig(timeout=1, interval=1),
    )
    if projection == "e2e":
        options["ui"] = None
    return {"backend": backend, "e2e": e2e}[projection].run(
        _load_document(raw), **options)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("observed,op", [
    (True, ">"), (False, "<="), (float("inf"), ">"),
    (float("-inf"), "<"), (float("nan"), ">"), ("1", ">"),
])
def test_span_ordering_never_promotes_boolean_or_nonfinite_observation(projection, observed, op):
    raw = request_document(state=[{
        "check": "span_attr", "span": "stored", "attr": "count",
        "op": op, "value": 0,
    }])
    result = execute(projection, raw, ObservedState({"count": observed}))
    checks = [check for check in result.checks if check.check == "span_attr"]
    assert result.status == "FAILED"
    assert len(checks) == 1 and not checks[0].ok
    assert result.steps[0].status != "ERROR"


@pytest.mark.parametrize("observed,expected,op,ok", [
    (1, 0, ">", True), (1.5, 1, ">", True),
    (-1, 0, "<", True), (0, 0, "<=", True),
    (1, 1.0, ">=", True), (10**400, 1e308, ">", True),
    (True, True, "==", True), (True, 1, "==", False),
    (False, 0, "==", False), (1, 1.0, "==", False),
])
def test_span_numeric_ordering_and_strict_equality_remain_distinct(observed, expected, op, ok):
    check = Assertion("span_attr", {
        "span": "stored", "attr": "count", "op": op, "value": expected})
    facts = ports.StateFacts("trace", [ports.Span("stored", {"count": observed})])
    assert backend._eval_span(check, facts).ok is ok


def test_invalid_span_attribute_does_not_hide_a_different_valid_matching_span():
    check = Assertion("span_attr", {
        "span": "stored", "attr": "count", "op": ">", "value": 0})
    facts = ports.StateFacts("trace", [
        ports.Span("stored", {"count": "invalid"}),
        ports.Span("stored", {"count": 2}),
    ])
    assert backend._eval_span(check, facts).ok


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("policy,status", [("FAIL", "FAILED"), ("SKIP", "DEGRADED")])
@pytest.mark.parametrize("with_probe", [False, True])
def test_poll_timeout_lists_every_unevaluated_state_check_without_probing(
        projection, policy, status, with_probe):
    state_checks = [
        {"check": "span_exists", "span": "stored"},
        {"check": "span_attr", "span": "stored", "attr": "count", "op": ">", "value": 0},
    ]
    raw = request_document(
        response=[{"check": "field_equals", "field": "state", "value": "ready"}],
        state=state_checks, poll=policy)
    probe = ObservedState({"count": 1}) if with_probe else None
    result = execute(projection, raw, probe, response={"state": "pending"})
    assert result.status == status
    assert not [check for check in result.checks if check.point == "backend_state"]
    assert len(result.steps[0].not_checked) == len(state_checks)
    for declaration, reason in zip(state_checks, result.steps[0].not_checked, strict=True):
        assert declaration["check"] in reason
        assert "poll" in reason and "terminal response" in reason
    assert probe is None or probe.calls == []
    assert not result.steps[0].response_origin.is_final
    assert result.steps[0].response_origin.timed_out


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_ready_poll_still_observes_selected_state(projection):
    raw = request_document(
        response=[{"check": "field_equals", "field": "state", "value": "ready"}],
        state=[{"check": "span_exists", "span": "stored"}], poll="FAIL")
    probe = ObservedState({})
    result = execute(projection, raw, probe, response={"state": "ready"})
    assert result.status == "PASSED"
    assert probe.calls
    assert result.steps[0].not_checked == []
    assert any(check.point == "backend_state" and check.ok for check in result.checks)


@pytest.mark.parametrize("raw,expected", [
    ("a=1&", {"a": "1"}), ("&a=1", {"a": "1"}),
    ("a=1&&b=2", {"a": "1", "b": "2"}), ("&&", {}),
    ("empty&&blank=&", {"empty": "", "blank": ""}),
    ("a=%26&&", {"a": "&"}),
])
def test_observed_query_empty_separators_are_not_empty_keys(raw, expected):
    assert parse_query(raw) == expected


@pytest.mark.parametrize("raw", [
    "=value&", "&&=&&", "a=1&&a=2", "a=1&%61=2&",
    "&&a=%", "&&a=%FF",
])
def test_query_separator_tolerance_does_not_accept_ambiguous_or_malformed_values(raw):
    with pytest.raises(ValueError):
        parse_query(raw)


def test_minimal_example_parameter_controls_both_request_and_assertion(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/minimal/scenarios/create_and_delete.yaml"
    raw = yaml.safe_load(source.read_text())
    raw["parameters"]["item_name"] = "changed-record-name"
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw))
    adapters = build_adapters()
    result = runner.run_scenario(path, adapters, projections=("backend", "contract"))
    assert result.status == "PASSED"
    assert result.degradations() == []
    assert adapters.api.sent[0].body == {"name": "changed-record-name"}
