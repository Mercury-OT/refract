"""Continuation preserves failures and distinguishes unavailable dependencies."""
import dataclasses

import pytest

from refracto.declaration.loader import DeclarationError, _load_document
from refracto.declaration.model import Assertion, Expect, RequestTemplate, Scenario, Step, PollPolicy
from refracto.projection import backend
from refracto.report import BLOCKED, COMPLETED, DEGRADED, ERROR, FAILED, PASSED, SKIPPED, CheckResult, DomainResult, RunReport, StepResult
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder


def scenario():
    return Scenario("continue", None, "editor", [], [], "", [
        Step("first", RequestTemplate("GET", "first"), Expect(response=[Assertion("success")])),
        Step("second", RequestTemplate("GET", "second"), Expect(response=[Assertion("success")])),
    ])


def run(flow):
    from refracto.ports import RequestSpec
    api = FakeApi(responses={
        ("GET", "first"): {"status": 200, "json": {"success": False, "data": {"id": 7}}},
        ("GET", "second"): {"status": 200, "json": {"success": True, "data": {}}},
    })
    result = backend.run(flow, auth=FakeAuth(), api=api, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer(),
        resolve_request=lambda template: RequestSpec(template.method, template.path, template.body))
    return result


def test_default_failed_continues_and_keeps_failed_domain():
    result = run(scenario())
    assert [s.status for s in result.steps] == [FAILED, PASSED]
    assert result.steps[1].after_failures == ["first"]
    assert result.status == FAILED


def test_schema_one_accepts_explicit_stop():
    raw = {"schema_version": 1, "scenario": "stop", "users": ["editor"], "steps": [
        {"id": "first", "on_failure": "stop", "do": {"request": {"method": "GET", "path": ["first"]}},
         "expect": {"response": [{"check": "success"}]}}
    ]}
    assert _load_document(raw).steps[0].on_failure == "stop"


def document(steps):
    return {"schema_version": 1, "scenario": "references", "users": ["editor"], "steps": steps}


def request(sid, path=None, checks=None, **extra):
    return {"id": sid, "do": {"request": {"method": "GET", "path": path or [sid]}},
            "expect": {"response": checks or [{"check": "success"}]}, **extra}


def execute(raw, responses=None, *, api=None, normalizer=None, **kwargs):
    from refracto.ports import RequestSpec
    flow = _load_document(raw) if isinstance(raw, dict) else raw
    api, recorder = api or FakeApi(responses), FakeRecorder()
    result = backend.run(flow, auth=FakeAuth(), api=api, state=None, recorder=recorder,
        normalizer=normalizer or FakeNormalizer(),
        resolve_request=lambda template: RequestSpec(template.method, template.path, template.body), **kwargs)
    return result, api, recorder


def test_stop_is_opt_in_and_names_the_stop_source():
    flow = scenario()
    flow.steps[0].on_failure = "stop"
    result = run(flow)
    assert [s.status for s in result.steps] == [FAILED, BLOCKED]
    assert result.steps[1].blocked_by == ["first"]
    assert result.steps[1].after_failures == []


@pytest.mark.parametrize("policy", [None, False, True, 0, "continue", "STOP", "", [], {}, {"from_parameter": "policy"}])
def test_only_explicit_literal_stop_is_allowed(policy):
    with pytest.raises(DeclarationError, match="on_failure"):
        _load_document(document([request("first", on_failure=policy)]))


def test_format_two_is_not_introduced():
    raw = document([request("first")])
    raw["schema_version"] = 2
    with pytest.raises(DeclarationError, match="integer 1"):
        _load_document(raw)


def test_expansion_shows_effective_policy():
    from refracto.declaration.expansion import expansion_view
    flow = _load_document(document([request("first"), request("second", on_failure="stop")]))
    assert [s["on_failure"] for s in expansion_view(flow)["steps"]] == ["continue", "stop"]


@pytest.mark.parametrize("data", [{}, {"id": None}, {"id": []}, {"id": True}, {"id": ""}])
def test_unavailable_reference_blocks_only_consumers_and_preserves_atomicity(data):
    raw = document([
        request("source", checks=[{"check": "has", "field": "id"}]),
        request("consumer", ["objects", {"from_step": "source", "response_field": "id"}],
                checks=[{"check": "has", "field": "id"}], on_failure="stop"),
        request("dependent", ["objects", {"from_step": "consumer", "response_field": "id"}]),
        request("independent"),
    ])
    result, api, _ = execute(raw, {("GET", "source"): {"json": {"success": True, "data": data}}})
    assert [s.status for s in result.steps[1:]] == [BLOCKED, BLOCKED, PASSED]
    assert [s.path for s in api.sent] == ["source", "independent"]
    assert result.steps[1].blocked_by == ["source"]
    assert result.steps[2].blocked_by == ["consumer"]
    assert result.steps[1].resolved_bindings == {}
    assert result.status != PASSED


@pytest.mark.parametrize("value", [False, 0, ""])
def test_valid_falsy_response_in_body_and_check_remains_usable(value):
    raw = document([
        request("source", checks=[{"check": "has", "field": "id"}]),
        request("consumer", checks=[{"check": "field_equals", "field": "id", "value": {"from_step": "source", "response_field": "id"}}]),
    ])
    raw["steps"][1]["do"]["request"]["body"] = {"nested": [{"from_step": "source", "response_field": "id"}]}
    responses = {( "GET", sid): {"json": {"success": True, "data": {"id": value}}} for sid in ("source", "consumer")}
    result, api, _ = execute(raw, responses)
    assert result.status == PASSED
    assert api.sent[1].body == {"nested": [value]}
    assert len(result.steps[1].binding_sources) == 1
    source = next(iter(result.steps[1].binding_sources.values()))
    assert source.response_field == "id" and source.origin.step_id == "source"
    assert source.origin.is_final and not source.origin.timed_out


def test_failed_source_response_is_usable_and_assertion_free_actions_are_labelled():
    raw = document([
        request("source", checks=[{"check": "success"}, {"check": "has", "field": "id"}]),
        {"id": "pause", "do": "wait", "duration": 0},
        request("consumer", ["objects", {"from_step": "source", "response_field": "id"}]),
    ])
    result, api, _ = execute(raw, {("GET", "source"): {"json": {"success": False, "data": {"id": 7}}}})
    assert [s.status for s in result.steps] == [FAILED, COMPLETED, PASSED]
    assert result.steps[1].after_failures == ["source"]
    assert result.steps[2].after_failures == ["source"]
    assert api.sent[1].path == "objects/7"


@pytest.mark.parametrize("failure", [ValueError("unexpected"), KeyError("unexpected")])
def test_unexpected_execution_exceptions_are_errors_and_stop(failure):
    class Broken(FakeApi):
        def send(self, spec, session):
            raise failure
    result, _, _ = execute(scenario(), api=Broken())
    assert [s.status for s in result.steps] == [ERROR, BLOCKED]


def test_dependency_exception_from_port_is_not_reclassified_as_recoverable():
    from refracto.declaration.binding import InvalidDependency
    class Broken(FakeApi):
        def send(self, spec, session):
            raise InvalidDependency("adapter error", ["first"])
    result, _, _ = execute(scenario(), api=Broken())
    assert [s.status for s in result.steps] == [ERROR, BLOCKED]


def test_malformed_normalizer_shape_is_error_not_dependency_block():
    class Broken(FakeNormalizer):
        def normalize(self, response):
            result = super().normalize(response)
            result.fields = []
            return result
    raw = document([request("first", checks=[{"check": "has", "field": "id"}]),
                    request("second", ["objects", {"from_step": "first", "response_field": "id"}])])
    result, _, _ = execute(raw, normalizer=Broken())
    assert [s.status for s in result.steps] == [ERROR, BLOCKED]
    assert result.status == FAILED


@pytest.mark.parametrize("timeout,stop,expected", [("FAIL", False, [FAILED, PASSED]), ("FAIL", True, [FAILED, BLOCKED]), ("SKIP", False, [SKIPPED, BLOCKED])])
def test_poll_timeout_preserves_last_response_provenance(timeout, stop, expected):
    from refracto.runner import PollConfig
    from tests.test_backend_resolved_bindings import FakeClock
    raw = document([
        request("source", checks=[{"check": "has", "field": "id"}, {"check": "field_equals", "field": "ready", "value": True}],
                poll={"on_timeout": timeout}, **({"on_failure": "stop"} if stop else {})),
        request("consumer", ["objects", {"from_step": "source", "response_field": "id"}]),
    ])
    clock = FakeClock()
    result, _, recorder = execute(raw, {("GET", "source"): {"json": {"success": True, "data": {"id": 7, "ready": False}}}},
        poll_config=PollConfig(timeout=1, interval=1), now=clock.now, sleep=clock.sleep)
    assert [s.status for s in result.steps] == expected
    origin = result.steps[0].response_origin
    assert origin.step_id == "source" and origin.timed_out and not origin.is_final
    assert origin.attempt_index == result.steps[0].attempts - 1
    assert not any(r.is_final for r in recorder.responses() if r.step_id == "source")
    if expected[1] == PASSED:
        assert next(iter(result.steps[1].binding_sources.values())).origin == origin


def test_report_blocked_never_passes_and_keyword_only_metadata_is_isolated():
    passed = StepResult("passed", PASSED, checks=[CheckResult("response", "success", True)])
    blocked = StepResult("blocked", BLOCKED, blocked_by=["source"])
    domain = DomainResult("backend", [passed, blocked])
    report = RunReport("report", [domain])
    assert domain.status == report.status == DEGRADED
    assert report.degradations() == [("backend", "blocked", "step was blocked: source")]
    assert "after_failures" not in StepResult.__match_args__
    assert StepResult("a", PASSED).after_failures is not StepResult("b", PASSED).after_failures
    fields = {field.name: field for field in dataclasses.fields(StepResult)}
    assert all(fields[name].kw_only and not fields[name].compare
               for name in ("after_failures", "blocked_by", "response_origin", "binding_sources"))


@pytest.mark.parametrize("stop", [False, True])
def test_included_failed_leaf_preserves_named_results_and_child_stop_policy(tmp_path, stop):
    from tests.test_scenario_named_results import bundle, child, include, named, request as child_request, run_backend
    raw = child()
    if stop:
        raw["steps"][0]["on_failure"] = "stop"
    path, _ = bundle(tmp_path, child_raw=raw, steps=[include(), child_request("read", path=["items", named()])])
    result, api = run_backend(path, {("POST", "items"): {"json": {"success": False, "data": {"id": 7}}}})
    steps = result.domains[0].steps
    assert [step.status for step in steps] == [FAILED, BLOCKED if stop else PASSED]
    assert len(api.sent) == (1 if stop else 2)
    if stop:
        assert steps[1].blocked_by == ["setup/create"]
    else:
        assert steps[1].after_failures == ["setup/create"]
        assert next(iter(steps[1].binding_sources.values())).origin.step_id == "setup/create"
    assert result.status == FAILED


def test_include_call_cannot_override_policy(tmp_path):
    from refracto.declaration.loader import load_scenario
    from tests.test_scenario_named_results import bundle, include
    path, _ = bundle(tmp_path, steps=[include(on_failure="stop")])
    with pytest.raises(DeclarationError, match="on_failure"):
        load_scenario(path)


def test_policy_changes_are_visible_to_impact_review(tmp_path):
    from tests.test_scenario_impact import child, bundle, inspect
    changed = child()
    changed["steps"][0]["on_failure"] = "stop"
    report = inspect(bundle(tmp_path, new=changed))
    assert report["review_required"] is True
    assert any(item["location"] == "/steps/by-id/create/on_failure" for item in report["changes"])


@pytest.mark.parametrize("mode", ["mock", "live"])
def test_ui_local_dependency_block_has_no_action_and_independent_action_runs(mode):
    from refracto.declaration.model import Binding, ValueRef
    from tests.ui_support import ScriptedUi, run as ui_run, scenario as ui_scenario
    flow = ui_scenario(count=3)
    flow.steps[1].bind = [Binding("missing", "s0", "absent")]
    flow.steps[1].value = ValueRef("bind", "missing")
    ui = ScriptedUi(count=2)
    result = ui_run(flow, ui, mode=mode)
    assert [step.status for step in result.steps] == [PASSED, BLOCKED, PASSED]
    assert result.steps[1].blocked_by == ["s0"]
    assert [permit.step_id for permit in ui.permits] == ["s0", "s2"]
    assert ui.open_calls == ui.close_calls == 1
    assert result.status == DEGRADED
    if mode == "mock":
        assert len(result.mock_consumption) == 2


def test_blocked_ui_step_does_not_discard_next_unconsumed_mock_fixture():
    from refracto.ports import MockResponse
    from refracto.declaration.model import Binding
    from tests.ui_support import ScriptedUi, run as ui_run, scenario as ui_scenario, response
    flow = ui_scenario(count=3)
    flow.steps[1].bind = [Binding("missing", "s0", "absent")]
    ui = ScriptedUi(count=2)
    plan = ui.plan()
    plan.insert(1, MockResponse(fixture_id="blocked-fixture", source="explicit test", method="POST", path="different", response=response()))
    result = ui_run(flow, ui, mode="mock", mock_plan=plan)
    assert [step.status for step in result.steps] == [PASSED, BLOCKED, ERROR]
    assert [permit.step_id for permit in ui.permits] == ["s0", "s2"]
    assert len(result.mock_consumption) == 1


@pytest.mark.parametrize("shape", ["fields-list", "fields-key", "success-int", "wrong-object"])
@pytest.mark.parametrize("mode", ["backend", "poll", "live", "mock", "contract"])
def test_malformed_normalization_is_never_passing_evidence(shape, mode):
    from refracto.ports import RecordedResponse, RequestSpec
    from refracto.contract.store import provider_contract
    from tests.ui_support import ScriptedUi, run as ui_run, scenario as ui_scenario
    class Broken(FakeNormalizer):
        def normalize(self, response):
            norm = super().normalize(response)
            if shape == "fields-list": norm.fields = []
            elif shape == "fields-key": norm.fields = {1: "data"}
            elif shape == "success-int": norm.succeeded = 1
            else: return {"succeeded": True, "fields": {}}
            return norm
    if mode == "contract":
        from refracto.projection import contract
        response = RecordedResponse(200, {}, {}, "", None, RequestSpec("GET", "items"))
        with pytest.raises(ValueError, match="Normalizer"):
            provider_contract([response], Broken())
        result = contract.run(scenario(), [response], Broken())
        assert result.status == FAILED and result.steps[0].status == ERROR
        return
    if mode in ("live", "mock"):
        ui = ScriptedUi()
        result = ui_run(ui_scenario(), ui, mode=mode, normalizer=Broken())
        assert len(ui.permits) == 1
    else:
        flow = scenario()
        if mode == "poll": flow.steps[0].poll = PollPolicy("FAIL")
        result, api, _ = execute(flow, normalizer=Broken())
        assert len(api.sent) == 1
    assert [step.status for step in result.steps] == [ERROR, BLOCKED]


@pytest.mark.parametrize("failure_port", ["api", "normalizer", "recorder"])
@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_port_timeout_during_later_poll_attempt_is_error_not_budget_failure(failure_port, projection):
    from refracto import ports
    from refracto.runner import PollConfig
    from tests.test_backend_resolved_bindings import FakeClock
    class BrokenApi(FakeApi):
        def send(self, spec, session):
            if failure_port == "api" and self.sent:
                raise TimeoutError("port failure, not polling budget")
            return super().send(spec, session)
    class BrokenNormalizer(FakeNormalizer):
        calls = 0
        def normalize(self, response):
            self.calls += 1
            if failure_port == "normalizer" and self.calls == 2:
                raise TimeoutError("port failure, not polling budget")
            return super().normalize(response)
    class BrokenRecorder(FakeRecorder):
        def record(self, response):
            if failure_port == "recorder" and self._responses:
                raise TimeoutError("port failure, not polling budget")
            return super().record(response)
    flow = scenario()
    flow.steps[0].poll = PollPolicy("FAIL")
    clock = FakeClock()
    api = BrokenApi({("GET", "first"): {"json": {"success": False}}})
    kwargs = dict(api=api, recorder=BrokenRecorder(), normalizer=BrokenNormalizer(),
        resolve_request=lambda t: ports.RequestSpec(t.method, t.path),
        poll_config=PollConfig(timeout=2, interval=1), now=clock.now, sleep=clock.sleep)
    if projection == "backend":
        result = backend.run(flow, auth=FakeAuth(), state=None, **kwargs)
    else:
        from tests.ui_support import run as ui_run
        result = ui_run(flow, None, **kwargs)
    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert result.steps[0].response_origin is None


@pytest.mark.parametrize("mode", ["backend", "live"])
def test_state_probe_timeout_is_not_retried_as_expired_poll_budget(mode):
    from refracto import ports
    from tests.ui_support import ScriptedUi, run as ui_run, scenario as ui_scenario
    class BrokenState(ports.StateProbe):
        calls = 0
        def observe(self, trace_id):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("observation transport failed")
            return ports.StateFacts(trace_id, [ports.Span("created")])
    state = BrokenState()
    if mode == "live":
        result = ui_run(ui_scenario(state=True), ScriptedUi(), state=state)
    else:
        flow = scenario()
        flow.steps[0].expect.backend_state = [Assertion("span_exists", {"span": "created"})]
        result = backend.run(flow, auth=FakeAuth(), api=FakeApi(), state=state, recorder=FakeRecorder(),
            normalizer=FakeNormalizer(), resolve_request=lambda t: ports.RequestSpec(t.method, t.path))
    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert state.calls == 1


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_nested_wait_inside_normalizer_is_not_the_outer_poll_budget(projection):
    from refracto import asyncwait, ports
    from refracto.runner import PollConfig
    from tests.test_backend_resolved_bindings import FakeClock
    class NestedWait(FakeNormalizer):
        calls = 0
        def normalize(self, response):
            self.calls += 1
            if self.calls == 2:
                # A real, separate helper invocation, not a manually forged exception.
                asyncwait.wait_until(lambda: (False, None), timeout=0, now=lambda: 0)
            return super().normalize(response)
    flow = scenario()
    flow.steps[0].poll = PollPolicy("FAIL")
    clock = FakeClock()
    api = FakeApi({("GET", "first"): {"json": {"success": False}}})
    kwargs = dict(api=api, recorder=FakeRecorder(), normalizer=NestedWait(),
        resolve_request=lambda t: ports.RequestSpec(t.method, t.path),
        poll_config=PollConfig(timeout=5, interval=1), now=clock.now, sleep=clock.sleep)
    if projection == "backend":
        result = backend.run(flow, auth=FakeAuth(), state=None, **kwargs)
    else:
        from tests.ui_support import run as ui_run
        result = ui_run(flow, None, **kwargs)
    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert [sent.path for sent in api.sent] == ["first", "first"]
    assert result.steps[0].response_origin is None


@pytest.mark.parametrize("callback", ["fn", "now", "sleep"])
def test_callback_wait_timeout_is_execution_error_without_sensitive_message(callback):
    from refracto import asyncwait
    def nested(*args):
        raise asyncwait.WaitTimeout("sensitive-nested-timeout")
    with pytest.raises(TimeoutError) as caught:
        asyncwait.wait_until(nested if callback == "fn" else lambda: (False, None),
            timeout=1, now=nested if callback == "now" else lambda: 0,
            sleep=nested if callback == "sleep" else lambda seconds: None)
    assert not isinstance(caught.value, asyncwait.WaitTimeout)
    assert "sensitive-nested-timeout" not in str(caught.value)
