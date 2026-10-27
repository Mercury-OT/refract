"""Action interfaces carry operations, not the declarations used to judge them."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass
import hashlib
import inspect
import json
from types import SimpleNamespace

import pytest
import yaml

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Assertion, Expect, Scenario, Step
from refracto.projection import backend, frontend
from refracto.query import wire_query
from refracto.report import BLOCKED, ERROR, FAILED, PASSED
from refracto.runner import Adapters, PollConfig, run_scenario
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeStateProbe
from tests.ui_support import ScriptedUi, rendered, response


REQUEST_FIELDS = {"method", "path", "body", "query", "headers"}
PERMIT_FIELDS = {"execution_id", "action_id", "step_id", "mode", "action", "target",
                 "value", "token", "user", "session_generation", "context_id"}
TRANSPORT_FIELDS = {ports.RequestAction: REQUEST_FIELDS, ports.UiActionPermit: PERMIT_FIELDS,
                    ports.MockResponse: {item.name for item in fields(ports.MockResponse)},
                    ports.MockResponseQueue: {"plan", "index"}}


def inspect_operation_data(value):
    """Walk only core transport values and data, never arbitrary external handles."""
    assert not isinstance(value, (Scenario, Step, Expect, Assertion))
    if is_dataclass(value):
        assert type(value) in TRANSPORT_FIELDS
        assert {item.name for item in fields(value)} == TRANSPORT_FIELDS[type(value)]
        return {item.name: inspect_operation_data(getattr(value, item.name))
                for item in fields(value)}
    if type(value) is dict:
        return {key: inspect_operation_data(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [inspect_operation_data(item) for item in value]
    assert value is None or type(value) in (str, int, float, bool)
    return value


def document(steps, *, parameters=None):
    return {"schema_version": 1, "scenario": "records.action_boundary", "users": [],
            "parameters": parameters or {}, "steps": steps}


def api_step(identity="create", *, body=None, checks=None):
    request = {"method": "POST", "path": ["records"]}
    if body is not None:
        request["body"] = body
    return {"id": identity, "do": {"request": request},
            "expect": {"response": checks or [{"check": "success"}]}}


def write(tmp_path, declaration, name="scenario.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


def resolve(action):
    return ports.RequestSpec(action.method, action.path, deepcopy(action.body),
                             query=wire_query(action.query or {}),
                             headers=deepcopy(action.headers or {}))


class EvidenceApi(FakeApi):
    def send(self, spec, session):
        result = super().send(spec, session)
        result.request_header_items = list(spec.headers.items())
        result.header_items = list(result.headers.items())
        return result


def adapters(*, resolver=resolve, api=None, ui=None, state=None):
    return Adapters(FakeAuth(), api or EvidenceApi(), state, ui, FakeRecorder, resolver,
                    FakeNormalizer())


class State(FakeStateProbe):
    def observe(self, trace_id):
        return ports.StateFacts(trace_id, [ports.Span("changed", {"value": "observed-state"})])


class Clock:
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class SpyUi(ScriptedUi):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.operation_inputs = []
        self.open_inputs = []

    def open_stepwise(self, session, **kwargs):
        self.open_inputs.append(inspect_operation_data(kwargs))
        return super().open_stepwise(session, **kwargs)

    def perform_step(self, context, permit, *, business_header_names=()):
        self.operation_inputs.append(inspect_operation_data(
            {"permit": permit, "business_header_names": business_header_names}))
        result = super().perform_step(context, permit, business_header_names=business_header_names)
        for traffic in result.evidence.traffic:
            traffic.response.request_header_items = list(traffic.request.headers.items())
            traffic.response.header_items = list(traffic.response.headers.items())
        return result


def test_interface_and_transport_field_allowlists():
    assert set(inspect.signature(ports.StepwiseUiDriver.open_stepwise).parameters) == {
        "self", "session", "mode", "mock_plan", "mock_queue", "user",
        "session_generation", "context_id"}
    assert set(inspect.signature(ports.StepwiseUiDriver.perform_step).parameters) == {
        "self", "context", "permit", "business_header_names"}
    assert {item.name for item in fields(ports.RequestAction)} == REQUEST_FIELDS
    assert {item.name for item in fields(ports.UiActionPermit)} == PERMIT_FIELDS
    action = ports.RequestAction(method="POST", path="records", body={"expect": ["data"]})
    assert inspect_operation_data(action)["body"] == {"expect": ["data"]}
    assert not hasattr(action, "__dict__")
    with pytest.raises(FrozenInstanceError):
        action.path = "changed"


@pytest.mark.parametrize("wrapper", [lambda bad: bad, lambda bad: {"metadata": [bad]},
                                    lambda bad: SimpleNamespace(metadata=bad)])
def test_structural_probe_rejects_nested_and_repackaged_assertions(wrapper):
    with pytest.raises(AssertionError):
        inspect_operation_data(wrapper(Assertion("success")))


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_real_runner_resolver_has_only_prepared_request_data(tmp_path, projection):
    sentinels = ["expected-response-only", "expected-state-only", "unused-parameter-only",
                 "future-expectation-only"]
    first = api_step(body={"expect": {"literal": ["business-input", False, 0]}})
    first["do"]["request"]["query"] = {"limit": 1, "blank": ""}
    first["do"]["request"]["headers"] = {"X-Key": "business-key"}
    first["expect"]["response"] = [{"check": "field_equals", "field": "name", "value": sentinels[0]}]
    first["expect"]["backend_state"] = [
        {"check": "span_attr", "span": "changed", "attr": "value", "op": "==", "value": sentinels[1]}]
    later = api_step("later", checks=[{"check": "field_equals", "field": "name", "value": sentinels[3]}])
    raw = document([first, later], parameters={"unused": sentinels[2]})
    seen = []

    def mapper(action):
        seen.append(inspect_operation_data(action))
        return resolve(action)

    clock = Clock()
    result = run_scenario(write(tmp_path, raw), adapters(resolver=mapper, state=State()),
                          projections=(projection,), poll_config=PollConfig(.001, .001),
                          now=clock.now, sleep=clock.sleep)
    assert result.status == FAILED
    assert len(seen) == 2
    assert seen[0] == {"method": "POST", "path": "records",
                       "body": {"expect": {"literal": ["business-input", False, 0]}},
                       "query": {"limit": 1, "blank": ""}, "headers": {"X-Key": "business-key"}}
    assert all(sentinel not in json.dumps(seen) for sentinel in sentinels)


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_real_runner_ui_does_not_receive_request_or_any_assertion_values(tmp_path, projection):
    expected = {"frontend": "expected-ui-only", "response": "expected-response-only",
                "backend_state": "expected-state-only"}
    step = {"id": "create", "do": "click", "target": "records.save", "expect": {
        "request": {"method": "POST", "path": ["items"], "headers": {"X-Z": "expected-header-only", "x-a": "another-header"}},
        "ui": [{"check": "objects_matching_count", "anchor": "rows", "field": "name",
                      "value": expected["frontend"], "count": 1}],
        "response": [{"check": "field_equals", "field": "name", "value": expected["response"]}],
        "backend_state": [{"check": "span_attr", "span": "changed", "attr": "value", "op": "==",
                           "value": expected["backend_state"]}]}}
    ui = SpyUi(1)
    result = run_scenario(write(tmp_path, document([step], parameters={"unused": "unused-only"})),
                          adapters(ui=ui, state=State()), projections=(projection,),
                          mock_plan=ui.plan() if projection == "frontend" else None,
                          poll_config=PollConfig(.001, .001))
    assert result.status == FAILED
    assert len(ui.operation_inputs) == 1
    assert ui.operation_inputs[0]["business_header_names"] == ["x-a", "x-z"]
    visible = json.dumps(ui.open_inputs + ui.operation_inputs)
    assert all(value not in visible for value in [*expected.values(), "expected-header-only", "unused-only"])
    assert ui.close_calls == 1


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_included_expectations_and_unused_child_parameters_do_not_reach_mapper(tmp_path, projection):
    child = document([api_step(checks=[{"check": "field_equals", "field": "name", "value": "child-expected-only"}])],
                     parameters={"unused": "child-unused-only"})
    child["scenario"] = "records.child_boundary"
    child_path = write(tmp_path, child, "child.yaml")
    parent_path = write(tmp_path, document([{"id": "setup", "do": {"include": child["scenario"]}}]))
    parent_path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {child["scenario"]: {"path": "child.yaml", "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    seen = []

    def mapper(action):
        seen.append(inspect_operation_data(action))
        return resolve(action)

    result = run_scenario(parent_path, adapters(resolver=mapper), projections=(projection,))
    assert result.status == FAILED
    assert result.domains[0].steps[0].step_id == "setup/create"
    assert len(seen) == 1
    assert "child-expected-only" not in json.dumps(seen)
    assert "child-unused-only" not in json.dumps(seen)


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_assertion_only_response_binding_stays_in_core_report(tmp_path, projection):
    secret = "assertion-reference-only"
    steps = [{"id": "source", "do": "click", "target": "records.save", "expect": {
                 "request": {"method": "POST", "path": ["items"]},
                 "response": [{"check": "has", "field": "secret"}]}},
             {"id": "check", "do": "fill", "target": "records.input", "value": "ordinary-input",
              "expect": {"ui": [{"check": "objects_matching_count", "anchor": "rows",
                  "field": "name", "value": {"from_step": "source", "response_field": "secret"}, "count": 1}]}}]
    ui = SpyUi(2, payloads=[response({"secret": secret}), response()],
               requests=[[ports.RequestSpec("POST", "items", {"name": "alpha"})], []],
               renders=[rendered(), rendered(secret)])
    result = run_scenario(write(tmp_path, document(steps)), adapters(ui=ui), projections=(projection,),
                          mock_plan=ui.plan() if projection == "frontend" else None)
    assert result.status == PASSED
    check = result.domains[0].steps[1]
    assert secret in check.resolved_bindings.values()
    assert next(iter(check.binding_sources.values())).origin.step_id == "source"
    assert secret not in json.dumps(ui.operation_inputs[1])
    assert "resolved_bindings" not in ui.operation_inputs[1]["permit"]
    assert secret not in repr(result)


def test_equal_action_and_expected_value_is_not_removed(tmp_path):
    value = "ordinary-action-and-expectation"
    step = {"id": "fill", "do": "fill", "target": "records.input", "value": value,
            "expect": {"ui": [{"check": "objects_matching_count", "anchor": "rows",
                "field": "name", "value": value, "count": 1}]}}
    ui = SpyUi(1, requests=[[]], renders=[rendered(value)])
    result = run_scenario(write(tmp_path, document([step])), adapters(ui=ui),
                          projections=("frontend",), mock_plan=[])
    assert result.status == PASSED
    assert ui.operation_inputs[0]["permit"]["value"] == value


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_equal_request_and_expected_value_remains_a_legitimate_input(tmp_path, projection):
    value = "ordinary-request-and-expectation"
    seen = []

    def mapper(action):
        seen.append(inspect_operation_data(action))
        return resolve(action)

    raw = document([api_step(body={"name": value}, checks=[
        {"check": "field_equals", "field": "name", "value": value}])])
    api = EvidenceApi({("POST", "records"): {"json": {"success": True, "data": {"name": value}}}})
    result = run_scenario(write(tmp_path, raw), adapters(resolver=mapper, api=api), projections=(projection,))
    assert result.status == PASSED
    assert seen[0]["body"] == {"name": value}


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_different_valid_expectations_leave_resolver_input_equal(tmp_path, projection):
    captures = []
    for expected in ("first-expectation", "second-expectation"):
        seen = []

        def mapper(action):
            seen.append(inspect_operation_data(action))
            return resolve(action)

        raw = document([api_step(body={"name": "fixed-input"}, checks=[
            {"check": "field_equals", "field": "name", "value": expected}])])
        run_scenario(write(tmp_path, raw), adapters(resolver=mapper), projections=(projection,))
        captures.append(seen)
    assert captures[0] == captures[1]
    assert captures[0][0]["body"] == {"name": "fixed-input"}


@pytest.mark.parametrize("field", ["body", "query", "headers"])
def test_mutating_request_view_cannot_move_the_comparison_baseline(tmp_path, field):
    step = api_step(body={"record": {"values": ["original", False, 0]}})
    step["do"]["request"].update(query={"key": "original"}, headers={"X-Key": "original"})
    loaded = load_scenario(write(tmp_path, document([step, api_step("later")])))
    before = deepcopy(loaded)
    api = FakeApi()

    def mapper(action):
        if field == "body":
            action.body["record"]["values"][0] = "changed"
        else:
            getattr(action, field)["key" if field == "query" else "X-Key"] = "changed"
        return resolve(action)

    result = backend.run(loaded, auth=FakeAuth(), api=api, state=None,
                         recorder=FakeRecorder(), normalizer=FakeNormalizer(), resolve_request=mapper)
    assert [step.status for step in result.steps] == [ERROR, BLOCKED]
    assert not api.sent
    assert loaded == before
    assert "resolver changed" in result.steps[0].detail


def test_retained_nested_view_does_not_mutate_later_declaration_or_past_recordings(tmp_path):
    raw = document([api_step("first", body={"data": [{"value": "original"}]}),
                    api_step("second", body={"data": [{"value": "original"}]})])
    loaded = load_scenario(write(tmp_path, raw))
    before = deepcopy(loaded)
    retained = []

    def mapper(action):
        if retained:
            retained[0].body["data"][0]["value"] = "changed-after-first"
        retained.append(action)
        return ports.RequestSpec(action.method, action.path, action.body)

    result = backend.run(loaded, auth=FakeAuth(), api=FakeApi(), state=None,
                         recorder=FakeRecorder(), normalizer=FakeNormalizer(), resolve_request=mapper)
    assert result.status == PASSED
    assert loaded == before
    assert all(r.request.body == {"data": [{"value": "original"}]} for r in result.provider_recordings)
    snapshot = deepcopy(result)
    retained[-1].body["data"].clear()
    assert result == snapshot


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("field", ["body", "query", "headers"])
@pytest.mark.parametrize("callback", ["send", "normalize"])
def test_retained_resolver_alias_cannot_change_later_poll_attempts(tmp_path, projection, field, callback):
    step = api_step(body={"record": {"values": ["original"]}}, checks=[
        {"check": "field_equals", "field": "ready", "value": True}])
    step["do"]["request"].update(method="GET", query={"key": "original"}, headers={"X-Key": "original"})
    step["poll"] = {"on_timeout": "FAIL"}
    retained = []

    def mutate_view():
        view = retained[0]
        if field == "body":
            view.body["record"]["values"][0] = "changed-after-resolution"
        else:
            getattr(view, field)["key" if field == "query" else "X-Key"] = "changed-after-resolution"

    def mapper(action):
        retained.append(action)
        # Returning aliases is legal, but it must not retain ownership of the
        # baseline used by later sends or actual-request header checks.
        return ports.RequestSpec(action.method, action.path, action.body,
                                 query=action.query, headers=action.headers)

    class PollApi(EvidenceApi):
        def send(self, spec, session):
            result = super().send(spec, session)
            result.json = {"success": True, "data": {"ready": len(self.sent) == 2}}
            if callback == "send" and len(self.sent) == 1:
                mutate_view()
            return result

    class PollNormalizer(FakeNormalizer):
        def normalize(self, result):
            if callback == "normalize":
                mutate_view()
            return super().normalize(result)

    api = PollApi()
    ports_for_run = adapters(resolver=mapper, api=api)
    ports_for_run.normalizer = PollNormalizer()
    clock = Clock()
    result = run_scenario(write(tmp_path, document([step])), ports_for_run,
                          projections=(projection,), poll_config=PollConfig(3, 1),
                          now=clock.now, sleep=clock.sleep)
    assert result.status == PASSED
    assert len(api.sent) == 2
    for sent in api.sent:
        assert sent.body == {"record": {"values": ["original"]}}
        assert sent.query == {"key": "original"}
        assert sent.headers == {"X-Key": "original"}
    assert result.domains[0].steps[0].attempts == 2


@pytest.mark.parametrize("mutation", ["current", "retained"])
def test_ui_nested_action_mutation_does_not_rewrite_the_declaration(tmp_path, mutation):
    step = {"id": "first", "do": "fill", "target": "records.input",
            "value": {"data": [{"name": "original"}]},
            "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}}
    later = deepcopy(step)
    later["id"] = "later"
    loaded = load_scenario(write(tmp_path, document([step, later])))
    before = deepcopy(loaded)
    retained = []

    class Mutating(SpyUi):
        def perform_step(self, context, permit, *, business_header_names=()):
            if mutation == "current":
                permit.value["data"][0]["name"] = "changed-current"
            elif retained:
                retained[0].value["data"][0]["name"] = "changed-later"
                assert permit.value == {"data": [{"name": "original"}]}
            retained.append(permit)
            return super().perform_step(context, permit, business_header_names=business_header_names)

    ui = Mutating(2, requests=[[], []])
    result = frontend.run(loaded, ui=ui, normalizer=FakeNormalizer(), auth=FakeAuth(), mock_plan=[])
    assert loaded == before
    if mutation == "current":
        assert [step.status for step in result.steps] == [ERROR, BLOCKED]
        assert result.steps[0].detail == "action permit was modified"
    else:
        assert result.status == PASSED
        snapshot = deepcopy(result)
        retained[-1].value["data"].clear()
        assert result == snapshot


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_legacy_resolver_never_retried_with_declaration(tmp_path, projection):
    entered = []

    def legacy(scenario, step, template):
        entered.append(scenario)
        return resolve(template)

    api = FakeApi()
    result = run_scenario(write(tmp_path, document([api_step(), api_step("later")])),
                          adapters(resolver=legacy, api=api), projections=(projection,))
    assert [step.status for step in result.domains[0].steps] == [ERROR, BLOCKED]
    assert not api.sent and not entered
    assert result.domains[0].steps[0].detail == "Request resolver failed"


@pytest.mark.parametrize("where", ["open", "perform"])
def test_legacy_ui_signature_has_no_fallback_or_target_action(tmp_path, where):
    entered = []

    class Legacy(SpyUi):
        if where == "open":
            def open_stepwise(self, scenario, session, **kwargs):
                entered.append(scenario)
        else:
            def perform_step(self, scenario, step, context, permit):
                entered.append(scenario)

    ui = Legacy(1, requests=[[]])
    raw = document([{"id": "fill", "do": "fill", "target": "records.input", "value": "x",
                     "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}}])
    result = run_scenario(write(tmp_path, raw), adapters(ui=ui), projections=("frontend",), mock_plan=[])
    assert result.domains[0].steps[0].status == ERROR
    assert not entered and not ui.permits
    assert ui.close_calls == (0 if where == "open" else 1)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_resolver_input_repr_and_callback_error_omit_sensitive_values(tmp_path, projection):
    secret = "sensitive-operation-input"
    raw = document([api_step(body={"value": secret})])
    raw["steps"][0]["do"]["request"].update(path=["records", secret], query={"key": secret})
    seen = []

    def broken(action):
        seen.append(action)
        raise RuntimeError(action.body["value"])

    result = run_scenario(write(tmp_path, raw), adapters(resolver=broken), projections=(projection,))
    assert result.domains[0].steps[0].status == ERROR
    assert result.domains[0].steps[0].detail == "Request resolver failed"
    assert secret not in repr(seen[0]) + repr(result) + result.domains[0].steps[0].detail


@pytest.mark.parametrize("where", ["open", "perform"])
def test_ui_callback_error_does_not_copy_credentials_or_fill_values(tmp_path, where):
    secret = "sensitive-ui-input"

    class CredentialAuth(FakeAuth):
        def session(self, user):
            session = super().session(user)
            session.credentials["token"] = secret
            return session

    class Broken(SpyUi):
        def open_stepwise(self, session, **kwargs):
            if where == "open":
                raise RuntimeError(session["token"])
            return super().open_stepwise(session, **kwargs)

        def perform_step(self, context, permit, *, business_header_names=()):
            raise RuntimeError(permit.value)

    raw = document([{"id": "fill", "do": "fill", "target": "records.input", "value": secret,
                     "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}}])
    raw["users"] = ["member"]
    configured = adapters(ui=Broken(1))
    configured.auth = CredentialAuth()
    result = run_scenario(write(tmp_path, raw), configured, projections=("frontend",), mock_plan=[])
    assert result.domains[0].steps[0].status == ERROR
    assert result.domains[0].steps[0].detail == ("UI open failed" if where == "open" else "UI action failed")
    assert secret not in repr(result) + result.domains[0].steps[0].detail
