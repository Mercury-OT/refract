"""Literal HTTP status requirements use captured transport evidence only."""
import copy
import dataclasses

import pytest

from refracto import ports
from refracto.contract import store
from refracto.declaration import vocabulary
from refracto.declaration.loader import DeclarationError, _load_document
from refracto.declaration.model import Assertion
from refracto.projection import backend, contract
from refracto.runner import PollConfig
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.ui_support import ScriptedUi, run as run_ui


def check(value=201):
    return {"check": "status_equals", "value": value}


def request(sid="create", checks=None, **extra):
    return {"id": sid, "do": {"request": {"method": "GET", "path": [sid]}},
            "expect": {"response": [check()] if checks is None else checks}, **extra}


def load(checks=None, *, steps=None, **extra):
    return _load_document({"schema_version": 1, "scenario": "status.requirement", "users": ["reader"],
        "steps": steps if steps is not None else [request(checks=checks)], **extra})


def execute(scenario, status=201, *, projection="backend", normalizer=None, api=None, **kwargs):
    api = api or FakeApi({("GET", "create"): {"status": status, "json": {"success": True}}})
    normalizer = normalizer or FakeNormalizer()
    args = dict(api=api, normalizer=normalizer,
                resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, t.body), **kwargs)
    if projection == "e2e":
        return run_ui(scenario, None, **args), api
    return backend.run(scenario, auth=FakeAuth(), state=None, recorder=FakeRecorder(), **args), api


def recorded(status):
    return ports.RecordedResponse(status, {}, {"success": True}, "", "trace",
        ports.RequestSpec("GET", "create"), step_id="create", template_path="create",
        user="reader", session_generation=1)


def test_vocabulary_and_boundary_values():
    assert vocabulary.required_params("response", "status_equals") == ("value",)
    assert vocabulary.required_params("response", "status_in") == ("values",)
    for value in (100, 201, 599):
        assert load([check(value)]).steps[0].expect.response[0].params == {"value": value}
    choices = [599, 100, 204]
    assert load([{"check": "status_in", "values": choices}]).steps[0].expect.response[0].params == {"values": choices}


@pytest.mark.parametrize("value", [99, 600, True, False, 201.0, "201", None, [], {},
    {"from_parameter": "code"}, {"from_step": "source", "response_field": "status"}])
def test_status_equals_rejects_nonliteral_or_invalid_values(value):
    with pytest.raises(DeclarationError):
        load([check(value)], parameters={"code": 201})


@pytest.mark.parametrize("choices", [[], None, 201, "201", {}, [201, 201], [True], [False],
    [201.0], ["201"], [99], [600], [None], [[]], [{}], [{"from_parameter": "code"}]])
def test_status_in_rejects_invalid_sets(choices):
    with pytest.raises(DeclarationError):
        load([{"check": "status_in", "values": choices}], parameters={"code": 201})


@pytest.mark.parametrize("checks", [
    [{"check": "status_equals"}], [{"check": "status_in"}],
    [{"check": "status_equals", "value": 201, "extra": 1}],
    [{"check": "status_in", "values": [201], "value": 201}],
    [check(), check()], [check(), check(202)],
    [{"check": "status_in", "values": [201]}, {"check": "status_in", "values": [202]}],
    [check(), {"check": "status_in", "values": [200, 201]}],
])
def test_missing_extra_and_duplicate_constraints_rejected(checks):
    with pytest.raises(DeclarationError):
        load(checks)


@pytest.mark.parametrize("point", ["frontend", "request", "backend_state"])
def test_wrong_observation_point_rejected(point):
    step = request()
    step["expect"] = {point: [check()]}
    with pytest.raises(DeclarationError):
        load(steps=[step])


def test_requestless_status_requirement_rejected():
    with pytest.raises(DeclarationError):
        load(steps=[{"id": "open", "do": "open", "target": "page", "expect": {"response": [check()]}}])


@pytest.mark.parametrize("check_data,observed,ok", [
    (check(), 201, True), (check(), 200, False),
    ({"check": "status_in", "values": [200, 204]}, 204, True),
    ({"check": "status_in", "values": [200, 204]}, 201, False),
])
def test_evaluator_captured_fact_not_normalized_fields(check_data, observed, ok):
    assertion = Assertion(check_data["check"], {k: v for k, v in check_data.items() if k != "check"})
    norm = ports.NormalizedResponse(True, {"status": 201}, 201, recorded(201))
    result = backend._eval_response(assertion, norm, observed_status=observed)
    assert result.ok is ok and result.check == check_data["check"]


@pytest.mark.parametrize("observed", [None, True, False, 201.0, "sensitive-status-sentinel", {}, [], 99, 600])
def test_evaluator_requires_safe_valid_captured_status(observed):
    norm = ports.NormalizedResponse(True, {}, 201, recorded(201))
    with pytest.raises(ValueError, match="HTTP status evidence") as exc:
        backend._eval_response(Assertion("status_equals", {"value": 201}), norm, observed_status=observed)
    assert "sensitive-status-sentinel" not in str(exc.value)


def test_evaluator_does_not_fallback_when_capture_omitted():
    with pytest.raises(ValueError, match="HTTP status evidence"):
        backend._eval_response(Assertion("status_equals", {"value": 201}),
                              ports.NormalizedResponse(True, {}, 201, recorded(201)))


class MisleadingNormalizer:
    def __init__(self, normalized_status=201, succeeded=True):
        self.normalized_status, self.succeeded = normalized_status, succeeded

    def normalize(self, response):
        response.status = self.normalized_status
        response.step_id, response.template_path = "forged", "forged"
        response.request.method, response.request.path = "DELETE", "forged"
        return ports.NormalizedResponse(self.succeeded, {"status": self.normalized_status},
                                        self.normalized_status, recorded(self.normalized_status))


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("actual,normalized", [(201, 500), (500, 201)])
def test_execution_ignores_normalizer_status_and_mutation(projection, actual, normalized):
    scenario = load(steps=[request(), request("after", [{"check": "success"}])])
    result, api = execute(scenario, actual, projection=projection, normalizer=MisleadingNormalizer(normalized))
    assert [s.status for s in result.steps] == (["PASSED", "PASSED"] if actual == 201 else ["FAILED", "PASSED"])
    assert len(api.sent) == 2
    first = result.provider_recordings[0]
    assert (first.status, first.step_id, first.request.method, first.request.path) == (actual, "create", "GET", "create")


@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_normalized_failure_does_not_replace_exact_rejection_status(status):
    scenario = load([{"check": "failure"}, check(403)])
    result, _ = execute(scenario, status, normalizer=MisleadingNormalizer(403, succeeded=False))
    assert [c.ok for c in result.checks] == [True, status == 403]


@pytest.mark.parametrize("normalized_check,succeeded", [("success", True), ("failure", False)])
def test_success_failure_and_status_constraints_remain_independent(normalized_check, succeeded):
    scenario = load([{"check": normalized_check}, check(500)])
    result, _ = execute(scenario, 500, normalizer=MisleadingNormalizer(200, succeeded=succeeded))
    assert result.status == "PASSED"


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("actual", [201, 500])
def test_ui_mock_and_live_protect_status_from_normalizer(mode, actual):
    scenario = load(steps=[{"id": "create", "do": "click", "target": "submit", "expect": {
        "request": {"method": "POST", "path": ["records"]}, "response": [check()]}},
        {"id": "after", "do": "click", "target": "after"}])
    def mutate(index, result, permit):
        for traffic in result.evidence.traffic:
            traffic.response.status = actual
        return result
    ui = ScriptedUi(count=2, requests=[[ports.RequestSpec("POST", "records")], []], mutate=mutate)
    plan = ui.plan()
    plan[0] = dataclasses.replace(plan[0], status=actual)
    result = run_ui(scenario, ui, mode=mode, normalizer=MisleadingNormalizer(201),
                    **({"mock_plan": plan} if mode == "mock" else {}))
    assert [s.status for s in result.steps] == (["PASSED", "COMPLETED"] if actual == 201 else ["FAILED", "COMPLETED"])
    assert ui.open_calls == ui.close_calls == 1
    if mode == "mock":
        assert result.provider_recordings == []
    else:
        assert result.provider_recordings[0].status == actual


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("status", [True, 201.0, "sensitive-status-sentinel", None, 99, 600])
def test_invalid_observed_status_errors_and_blocks_safely(projection, status):
    result, api = execute(load(steps=[request(), request("after")]), status, projection=projection)
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert "HTTP status evidence" in result.steps[0].detail
    assert "sensitive-status-sentinel" not in result.steps[0].detail + repr(result)
    assert len(api.sent) == 1


@pytest.mark.parametrize("requirement,actual,ok", [
    (check(), 201, True), (check(), 200, False),
    ({"check": "status_in", "values": [200, 204]}, 204, True),
    ({"check": "status_in", "values": [200, 204]}, 201, False),
])
def test_contract_status_and_recording_identity_are_independent_of_normalizer(requirement, actual, ok):
    scenario, records = load([requirement]), [recorded(actual)]
    original = copy.deepcopy(records)
    result = contract.run(scenario, records, MisleadingNormalizer())
    assert (result.status == "PASSED") is ok
    assert records == original
    provider = store.provider_contract(records, MisleadingNormalizer())
    shape = provider.entries[("create", "GET", "create")]
    assert shape.http_status == actual
    consumer = store.consumer_contract(scenario).entries[("create", "GET", "create")]
    assert consumer.allowed_http_statuses == frozenset([requirement["value"]] if "value" in requirement else requirement["values"])


@pytest.mark.parametrize("status", [True, False, 201.0, "sensitive-status-sentinel", None, 99, 600])
def test_contract_missing_or_invalid_status_cannot_pass_or_leak(status):
    raw = recorded(status)
    result = contract.run(load(), [raw], MisleadingNormalizer())
    assert result.status == "FAILED"
    assert "HTTP status" in result.checks[0].detail
    assert "sensitive-status-sentinel" not in result.checks[0].detail + repr(result)
    provider = store.provider_contract([raw], MisleadingNormalizer())
    assert "sensitive-status-sentinel" not in repr(provider)


@pytest.mark.parametrize("status", [True, None, "sensitive-status-sentinel"])
def test_contract_rejects_invalid_status_before_normalizer(status):
    class ExplodingNormalizer:
        def normalize(self, response):
            raise AssertionError("sensitive-normalizer-sentinel")
    response = recorded(status)
    response.json = None
    result = contract.run(load(), [response], ExplodingNormalizer())
    assert result.status == "FAILED"
    assert "HTTP status evidence is missing or invalid" in result.checks[0].detail
    assert "sentinel" not in result.checks[0].detail + repr(result)
    # Without a status check the normalizer is called; its exception is an
    # execution ERROR, not a passing comparison or a leaked raw exception.
    result = contract.run(load([{"check": "success"}]), [response], ExplodingNormalizer())
    assert result.status == "FAILED" and result.steps[0].status == "ERROR"
    assert "sensitive-normalizer-sentinel" in result.steps[0].detail
    assert "sensitive-normalizer-sentinel" not in repr(result)


def test_contract_recording_with_missing_status_fails_before_normalization():
    response = recorded(201)
    del response.status
    result = contract.run(load(), [response], FakeNormalizer())
    assert result.status == "FAILED"
    assert "HTTP status evidence is missing or invalid" in result.checks[0].detail


def test_contract_missing_capture_unconstrained_compatibility_and_keyword_only_fields():
    shape = store.EndpointShape(frozenset(), {}, store.DONT_CARE, True)
    key = ("create", "GET", "create")
    provider = store.Contract({key: shape})
    assert store.diff(store.consumer_contract(load()), provider)
    assert store.diff(store.consumer_contract(load([{"check": "success"}])), provider) == []
    assert shape.allowed_http_statuses is None and shape.http_status is None
    assert "allowed_http_statuses" not in store.EndpointShape.__match_args__
    assert "http_status" not in store.EndpointShape.__match_args__


class Clock:
    def __init__(self): self.value = 0
    def now(self): return self.value
    def sleep(self, seconds): self.value += seconds


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("policy,ready", [("FAIL", True), ("FAIL", False), ("SKIP", False)])
def test_poll_status_uses_each_actual_attempt_and_final_contract(projection, policy, ready):
    scenario = load(steps=[request(poll={"on_timeout": policy}), request("after", [{"check": "success"}])])
    class Api(FakeApi):
        def send(self, spec, session):
            self.responses = {("GET", "create"): {"status": 201 if ready and self.sent else 202,
                "json": {"success": True}}}
            return super().send(spec, session)
    api, clock = Api(), Clock()
    result, _ = execute(scenario, api=api, projection=projection, normalizer=MisleadingNormalizer(),
        poll_config=PollConfig(timeout=1, interval=1), now=clock.now, sleep=clock.sleep)
    assert [s.status for s in result.steps] == (["PASSED", "PASSED"] if ready else
        (["FAILED", "PASSED"] if policy == "FAIL" else ["SKIPPED", "BLOCKED"]))
    records = [r for r in result.provider_recordings if r.step_id == "create"]
    assert [r.status for r in records] == [202, 201 if ready else 202]
    assert [r.attempt_index for r in records] == [0, 1]
    assert [r.is_final for r in records] == [False, ready]
    if policy == "FAIL" and not ready:
        assert "202" in result.steps[0].checks[0].detail
    if ready:
        assert contract.run(scenario, result.provider_recordings, MisleadingNormalizer()).status == "PASSED"
    else:
        assert store.provider_contract(records, MisleadingNormalizer()).entries == {}
