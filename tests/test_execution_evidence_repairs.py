"""Incomplete work and unrelated state must never masquerade as successful checks."""
import json
from types import SimpleNamespace

import pytest

from refracto import headers, ports
from refracto.declaration.loader import _load_document
from refracto.errors import ActionFailure, ActionFailureReason, safe_action_failure
from refracto.projection import backend, ui_stepwise
from refracto.report import (
    BLOCKED, COMPLETED, DEGRADED, EMPTY, ERROR, FAILED, PASSED, SKIPPED,
    CheckResult, DomainResult, FlowReport, FlowScenarioReport, RunReport, StepResult,
)
from refracto.runner import Adapters, run_flow, run_scenario
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeUi
from tests.test_flow_runtime import flow_path, scenario as flow_scenario, request


def adapters(api=None, state=None):
    return Adapters(FakeAuth(), api or FakeApi(), state, None, FakeRecorder,
        lambda action: ports.RequestSpec(action.method, action.path, action.body,
                                        query=action.query or {}, headers=action.headers or {}),
        FakeNormalizer())


def declaration(*, state=True, polling=False):
    first = request("read", path=["records"])
    first["do"]["request"]["method"] = "GET"
    if state:
        first["expect"]["backend_state"] = [{"check": "span_exists", "span": "record.read"}]
    if polling:
        first["poll"] = {"on_timeout": "FAIL"}
    return flow_scenario("neutral.read", [first, request("later")])


def run(tmp_path, raw, adapter, projection="backend", **kwargs):
    path = tmp_path / "scenario.yaml"
    path.write_text(json.dumps(raw))
    return run_scenario(path, adapter, projections=(projection,), **kwargs)


class Clock:
    def __init__(self): self.time = 0
    def now(self): return self.time
    def sleep(self, duration): self.time += duration


@pytest.mark.parametrize("step_status,expected", [
    (PASSED, PASSED), (FAILED, FAILED), (ERROR, FAILED),
    (BLOCKED, DEGRADED), (SKIPPED, DEGRADED), (COMPLETED, EMPTY),
])
def test_passed_is_strict_at_every_report_level(step_status, expected):
    checks = [CheckResult("response", "success", True)] if step_status == PASSED else []
    domain = DomainResult("backend", [StepResult("read", step_status, checks=checks)])
    scenario = FlowScenarioReport("neutral.read", [domain], node_id="read")
    flow = FlowReport("neutral.flow", "run", [scenario])
    for report in (domain, scenario, flow):
        assert report.status == expected
        assert report.passed is (expected == PASSED)


def test_missing_create_id_never_passes_and_sends_no_dependent_request(tmp_path):
    raw = flow_scenario("neutral.create_read", [
        request("create", path=["records"]),
        request("read", path=["records", {"from_step": "create", "response_field": "id"}]),
    ])
    adapter = adapters()
    result = run(tmp_path, raw, adapter)
    assert result.status == DEGRADED and result.passed is False
    assert [s.status for s in result.domains[0].steps] == [PASSED, BLOCKED]
    assert [s.path for s in adapter.api.sent] == ["records"]


@pytest.mark.parametrize("policy,later_status,sent", [
    ("stop", DEGRADED, ["records"]),
    ("continue", PASSED, ["records", "later"]),
])
def test_flow_keeps_existing_scheduling_but_no_longer_calls_degradation_passed(
        tmp_path, policy, later_status, sent):
    first = flow_scenario("neutral.create_read", [
        request("create", path=["records"]),
        request("read", path=["records", {"from_step": "create", "response_field": "id"}]),
    ])
    path = flow_path(tmp_path, [first, flow_scenario("neutral.later", [request("later")])], policy=policy)
    adapter = adapters()
    result = run_flow(path, adapter, projections=("backend",))
    assert result.status == DEGRADED and result.passed is False
    assert result.scenarios[0].passed is False
    assert result.scenarios[1].status == later_status
    assert [s.path for s in adapter.api.sent] == sent


class Probe:
    def __init__(self, shape="correct"):
        self.shape, self.calls, self.last = shape, [], None

    def observe(self, trace):
        self.calls.append(trace)
        facts = ports.StateFacts(trace, [ports.Span("record.read", {"data": [1]})])
        if self.shape in ("wrong", None, "", 1): facts.trace_id = self.shape
        if self.shape == "lookalike": facts = SimpleNamespace(trace_id=trace, spans=facts.spans)
        if self.shape == "empty": facts.spans = []
        if self.shape == "late_wrong":
            facts.spans = []
            if len(self.calls) > 1: facts.trace_id = "different-secret-trace"
        self.last = facts
        return facts


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("polling", [False, True])
@pytest.mark.parametrize("shape", ["wrong", None, "", 1, "lookalike"])
def test_wrong_or_malformed_state_cannot_pass_any_live_projection(tmp_path, projection, polling, shape):
    probe = Probe(shape)
    adapter = adapters(state=probe)
    result = run(tmp_path, declaration(polling=polling), adapter, projection)
    assert [s.status for s in result.domains[0].steps] == [ERROR, BLOCKED]
    assert result.status == FAILED and result.passed is False
    assert len(adapter.api.sent) == len(probe.calls) == 1
    assert "wrong" not in result.domains[0].steps[0].detail


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("polling", [False, True])
def test_correct_request_correlation_without_server_echo_remains_supported(tmp_path, projection, polling):
    class NoEcho(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.trace_id = None
            return response
    probe = Probe()
    adapter = adapters(NoEcho(), probe)
    result = run(tmp_path, declaration(polling=polling), adapter, projection)
    assert result.passed is True
    assert probe.calls == [adapter.api.sent[0].traceparent.split("-")[1]]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("polling", [False, True])
@pytest.mark.parametrize("trace", ["unrelated-secret-trace", "", 0, False])
def test_response_cannot_select_an_unrelated_trace(tmp_path, projection, polling, trace):
    class WrongEcho(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.trace_id = trace
            return response
    probe = Probe()
    adapter = adapters(WrongEcho(), probe)
    result = run(tmp_path, declaration(polling=polling), adapter, projection)
    assert [s.status for s in result.domains[0].steps] == [ERROR, BLOCKED]
    assert probe.calls == []
    assert "unrelated-secret-trace" not in repr(result)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("polling", [False, True])
def test_valid_nonmatching_state_is_failed_not_error_and_ordinary_continuation_remains(
        tmp_path, projection, polling):
    probe = Probe("empty")
    clock = Clock()
    result = run(tmp_path, declaration(polling=polling), adapters(state=probe), projection,
                 now=clock.now, sleep=clock.sleep)
    assert [step.status for step in result.domains[0].steps] == [FAILED, PASSED]
    assert result.passed is False
    assert clock.time == 30
    assert len(probe.calls) > 1


@pytest.mark.parametrize("helper", [backend.assert_backend_state_for, ui_stepwise._assert_live_backend_state_for])
def test_final_state_observation_after_timeout_also_checks_trace(helper):
    step = _load_document(declaration()).steps[0]
    probe = Probe("late_wrong")
    clock = Clock()
    with pytest.raises(ValueError):
        helper(step, probe, "current", state_timeout=0, now=clock.now, sleep=clock.sleep)
    assert probe.calls == ["current", "current"]


@pytest.mark.parametrize("helper", [backend.assert_backend_state_for, ui_stepwise._assert_live_backend_state_for])
@pytest.mark.parametrize("trace", [None, "", 0, False])
def test_unavailable_correlation_errors_before_probe(helper, trace):
    probe = Probe()
    with pytest.raises(ValueError):
        helper(_load_document(declaration()).steps[0], probe, trace)
    assert probe.calls == []


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_missing_probe_degrades_but_no_state_expectation_needs_no_probe(tmp_path, projection):
    result = run(tmp_path, declaration(), adapters(), projection)
    assert result.status == DEGRADED and result.passed is False
    probe = Probe("wrong")
    result = run(tmp_path, declaration(state=False), adapters(state=probe), projection)
    assert result.passed and probe.calls == []


def test_state_validation_returns_owned_snapshot_and_rechecks_copy():
    from refracto.state_evidence import validate_state_facts
    facts = ports.StateFacts("trace", [ports.Span("read", {"nested": [1]})])
    owned = validate_state_facts(facts, "trace")
    facts.spans[0].attributes["nested"].append(2)
    assert owned.spans[0].attributes["nested"] == [1]
    facts.__deepcopy__ = lambda memo: ports.StateFacts("other", [])
    with pytest.raises(ValueError): validate_state_facts(facts, "trace")


def throw(error):
    raise error


@pytest.mark.parametrize("reason", list(ActionFailureReason))
@pytest.mark.parametrize("cleanup", [False, True])
def test_fixed_action_reason_survives_core_wrapping_without_raw_exception_data(reason, cleanup):
    error = ActionFailure(reason, cleanup_failed=cleanup)
    error.args = ("secret-url-token-body",)
    assert "secret-url-token-body" not in str(error) + repr(error)
    with pytest.raises(ValueError) as captured:
        backend._call_action_port("UI action", throw, error)
    assert str(captured.value) == f"UI action failed ({reason.value}{'; cleanup_failed' if cleanup else ''})"


@pytest.mark.parametrize("mutation", ["reason", "cleanup", "subclass"])
def test_malformed_or_subclass_failure_uses_safe_generic_category(mutation):
    error = ActionFailure(ActionFailureReason.PAGE_ERROR)
    if mutation == "reason": error.reason = "secret-category"
    elif mutation == "cleanup": error.cleanup_failed = "secret-cleanup"
    else:
        subclass = type("secret-class", (ActionFailure,), {"__str__": lambda self: "secret-message"})
        error = subclass(ActionFailureReason.PAGE_ERROR)
    assert safe_action_failure(error) is None
    with pytest.raises(ValueError, match=r"^UI action failed \(RuntimeError\)$"):
        backend._call_action_port("UI action", throw, error)


@pytest.mark.parametrize("reason,cleanup", [("page_error", False), (None, False),
                                           (ActionFailureReason.PAGE_ERROR, 1)])
def test_failure_constructor_rejects_nonfinite_or_mistyped_category(reason, cleanup):
    with pytest.raises(ValueError, match="invalid action failure category"):
        ActionFailure(reason, cleanup_failed=cleanup)


def test_sensitive_header_wrapper_retains_only_explicit_safe_reason():
    safe = ActionFailure(ActionFailureReason.PAGE_ERROR, cleanup_failed=True)
    safe.args = ("secret-header-payload",)
    with pytest.raises(ValueError, match=r"^UI snapshot failed \(page_error; cleanup_failed\)$"):
        headers.call_port("UI snapshot", throw, safe, sensitive=True)
    safe.reason = "secret-category"
    with pytest.raises(ValueError, match="^UI snapshot failed while handling sensitive header data$"):
        headers.call_port("UI snapshot", throw, safe, sensitive=True)


@pytest.mark.parametrize("cleanup_error", [
    ActionFailure(ActionFailureReason.CLEANUP_FAILED),
    RuntimeError("secret-cleanup-message"),
])
def test_cleanup_keeps_primary_action_failure_and_never_exposes_raw_error(tmp_path, cleanup_error):
    class BrokenUi(FakeUi):
        def perform_step(self, *args, **kwargs):
            raise ActionFailure(ActionFailureReason.MOCK_BACKGROUND_BLOCKED)

        def close_stepwise(self, context):
            super().close_stepwise(context)
            raise cleanup_error

    raw = flow_scenario("neutral.page", [
        {"id": "open", "do": "open", "target": "records",
         "expect": {"ui": [{"check": "visible", "anchor": "records"}]}},
        {"id": "later", "do": "open", "target": "records"},
    ])
    adapter = adapters()
    adapter.ui = BrokenUi()
    result = run(tmp_path, raw, adapter, "e2e")
    assert [step.status for step in result.domains[0].steps] == [ERROR, BLOCKED]
    detail = result.domains[0].steps[0].detail
    assert "mock_background_blocked" in detail and "UI context close failed" in detail
    assert "secret-cleanup-message" not in repr(result)
    assert adapter.ui.close_calls == 1
