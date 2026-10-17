"""Action format cutover and projection-boundary regression tests."""
import copy

import pytest
import yaml

from refracto import ports, runner
from refracto.declaration import binding
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.projection import backend, contract
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder


def load(tmp_path, steps, **extra):
    document = {"schema_version": 1, "scenario": "actions", "users": ["reader"],
                "steps": steps, **extra}
    path = tmp_path / "actions.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return load_scenario(path)


def request(sid="read", method="GET", path=None, checks=None, **extra):
    return {"id": sid, "do": {"request": {"method": method, "path": path or ["records"]}},
            "expect": {"response": checks if checks is not None else [{"check": "success"}]}, **extra}


def execute(scenario, api=None, **extra):
    return backend.run(scenario, auth=FakeAuth(), api=api or FakeApi(), state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer(),
        resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, body=t.body),
        **extra)


@pytest.mark.parametrize("field,value", [
    ("version", 2), ("precondition", []), ("inputs", []), ("intent", "old"),
    ("schema_version", True), ("schema_version", "1"), ("schema_version", "proposed"),
])
def test_old_and_wrong_metadata_rejected(tmp_path, field, value):
    with pytest.raises(DeclarationError):
        load(tmp_path, [request()], **{field: value})


def test_duplicate_yaml_keys_rejected(tmp_path):
    p = tmp_path / "duplicate.yaml"
    p.write_text("schema_version: 1\nscenario: x\nscenario: y\n", encoding="utf-8")
    with pytest.raises(DeclarationError, match="duplicate"):
        load_scenario(p)


@pytest.mark.parametrize("steps", [[], [{"id": "a", "do": "click", "target": "submit"}],
    [request(checks=[])], [{"id": "a", "do": "wait", "duration": 0, "expect": {"ui": []}}]])
def test_scenario_without_assertions_rejected(tmp_path, steps):
    with pytest.raises(DeclarationError):
        load(tmp_path, steps)


@pytest.mark.parametrize("step", [
    {"id": "a", "do": "request"},
    {"id": "a", "do": "fill", "target": "field"},
    {"id": "a", "do": "open", "target": "page", "value": "extra"},
    {"id": "a", "do": "wait", "duration": True},
    {"id": "a", "do": "wait", "duration": -1},
    {"id": "a", "do": {"request": {"method": "GET", "path": "records"}}},
    {"id": "a", "do": {"request": {"method": "GET", "path": ["records"]}, "click": "button"}},
])
def test_one_primitive_and_strict_action_shape(tmp_path, step):
    with pytest.raises(DeclarationError):
        load(tmp_path, [step, request("checked")])


def test_api_does_not_accept_duplicate_request_expectation(tmp_path):
    step = request()
    step["expect"]["request"] = {"method": "GET", "path": ["records"]}
    with pytest.raises(DeclarationError):
        load(tmp_path, [step])


def test_no_check_request_can_supply_response_without_auto_assertion(tmp_path):
    source = request("source", "POST", checks=[])
    next_step = request("read", path=["records", {"from_step": "source", "response_field": "id"}])
    scenario = load(tmp_path, [source, next_step])
    api = FakeApi({("POST", "records"): {"json": {"success": True, "data": {"id": "a/b"}}}})
    result = execute(scenario, api)
    assert result.steps[0].status == "COMPLETED"
    assert result.steps[0].checks == []
    assert result.steps[1].status == "PASSED"
    assert api.sent[-1].path == "records/a%2Fb"
    assert scenario.steps[0].expect.response == []
    assert result.status == "PASSED"


@pytest.mark.parametrize("field_value", [0, False, ""])
def test_direct_response_values_keep_falsy_types(tmp_path, field_value):
    source = request("source", "POST", checks=[])
    target = request("target", "POST")
    target["do"]["request"]["body"] = {"value": {"from_step": "source", "response_field": "id"}}
    scenario = load(tmp_path, [source, target])
    api = FakeApi({("POST", "records"): {"json": {"success": True, "data": {"id": field_value}}}})
    result = execute(scenario, api)
    assert result.status == "PASSED"
    assert type(api.sent[1].body["value"]) is type(field_value)
    assert api.sent[1].body["value"] == field_value


def test_direct_refs_atomic_failure_and_no_partial_action(tmp_path):
    source = request("source", "POST", checks=[])
    target = request("target", "POST")
    target["do"]["request"]["body"] = {
        "first": {"from_step": "source", "response_field": "id"},
        "second": {"from_step": "source", "response_field": "missing"},
    }
    scenario = load(tmp_path, [source, target, request("blocked")])
    api = FakeApi({("POST", "records"): {"json": {"success": True, "data": {"id": "secret"}}}})
    result = execute(scenario, api)
    assert [s.status for s in result.steps] == ["COMPLETED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert len(api.sent) == 2


def test_references_in_fill_and_recursive_body_and_assertion(tmp_path):
    steps = [request("source"),
        {"id": "fill", "do": "fill", "target": "field",
         "value": {"from_step": "source", "response_field": "name"}},
        request("send", "POST", checks=[{"check": "field_equals", "field": "name",
            "value": {"from_parameter": "name"}}])]
    steps[-1]["do"]["request"]["body"] = {"nested": [{"from_parameter": "name"}]}
    scenario = load(tmp_path, steps, parameters={"name": "literal {braces}"})
    prior = {"source": ports.NormalizedResponse(True, {"name": "observed"}, 200, None)}
    filled, values = binding.prepare_step(scenario.steps[1], scenario, prior)
    assert filled.value == "observed"
    prepared, _ = binding.prepare_step(scenario.steps[2], scenario, prior)
    assert prepared.request.body == {"nested": ["literal {braces}"]}
    assert prepared.expect.response[0].params["value"] == "literal {braces}"


@pytest.mark.parametrize("ref", [
    {"from_step": "later", "response_field": "id"},
    {"from_step": "source", "response_field": "id"},
    {"from_parameter": "unknown"},
    {"from_parameter": "known", "extra": 1},
])
def test_bad_reference_scope_rejected(tmp_path, ref):
    step = request()
    step["do"]["request"]["body"] = {"value": ref}
    with pytest.raises(DeclarationError):
        load(tmp_path, [{"id": "source", "do": "open", "target": "page"}, step], parameters={"known": 1})


def test_backend_does_not_claim_ui_checks_and_wait_uses_milliseconds(tmp_path):
    scenario = load(tmp_path, [
        {"id": "page", "do": "open", "target": "page", "expect": {"ui": [{"check": "visible", "anchor": "row"}]}},
        {"id": "delay", "do": "wait", "duration": 125},
    ])
    api, delays = FakeApi(), []
    result = execute(scenario, api, sleep=delays.append)
    assert [s.status for s in result.steps] == ["NOT_APPLICABLE", "COMPLETED"]
    assert result.status == "EMPTY"
    assert not api.sent
    assert delays == [0.125]
    assert contract.run(scenario, [], FakeNormalizer()).status == "EMPTY"


def test_requestless_state_preflight_stops_all_side_effects(tmp_path):
    scenario = load(tmp_path, [request("first"), {"id": "observe", "do": "wait", "duration": 0,
        "expect": {"backend_state": [{"check": "span_exists", "span": "job"}]}}])
    api = FakeApi()
    result = execute(scenario, api)
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert not api.sent


@pytest.mark.parametrize("declared,actual,expected", [
    ({"a": [False]}, {"a": [0]}, False),
    ({"a": [True]}, {"a": [1]}, False),
    ({"a": [{"x": 1}]}, {"a": [{"x": 1, "extra": 2}], "extra": 0}, True),
    ({"a": [1]}, {"a": [1, 2]}, False),
])
def test_recursive_body_subset_is_type_strict(declared, actual, expected):
    assert backend._subset(declared, actual) is expected


def test_mapper_cannot_add_hidden_business_defaults(tmp_path):
    scenario = load(tmp_path, [request()])
    api = FakeApi()
    result = backend.run(scenario, auth=FakeAuth(), api=api, state=None,
        recorder=FakeRecorder(), normalizer=FakeNormalizer(),
        resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, body={"hidden": True}))
    assert result.steps[0].status == "ERROR"
    assert not api.sent


@pytest.mark.parametrize("policy", [True, "retry", None])
def test_poll_policy_is_explicit_and_bounded(tmp_path, policy):
    with pytest.raises(DeclarationError):
        load(tmp_path, [request(poll={"on_timeout": policy})])


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_poll_never_repeats_mutating_api_actions(tmp_path, method):
    with pytest.raises(DeclarationError):
        load(tmp_path, [request(method=method, poll={"on_timeout": "FAIL"})])


def test_poll_cannot_repeat_ui_action(tmp_path):
    with pytest.raises(DeclarationError):
        load(tmp_path, [{"id": "click", "do": "click", "target": "button",
            "poll": {"on_timeout": "FAIL"}, "expect": {
                "request": {"method": "GET", "path": ["records"]},
                "response": [{"check": "success"}]}}])


@pytest.mark.parametrize("value", [True, float("inf"), float("nan"), "1"])
def test_poll_config_rejects_nonfinite_and_ambiguous_timing(value):
    with pytest.raises(ValueError):
        runner.PollConfig(timeout=value)


def test_literal_brace_path_is_not_a_reference(tmp_path):
    scenario = load(tmp_path, [request(path=["records", "{literal}", {"from_parameter": "suffix"}])],
                    parameters={"suffix": "a/b ?"})
    prepared, resolved = binding.prepare_step(scenario.steps[0], scenario, {})
    assert prepared.request.path == "records/%7Bliteral%7D/a%2Fb%20%3F"
    assert resolved == {}


def test_response_reference_keys_cannot_alias(tmp_path):
    steps = [request("a.b", checks=[]), request("a", checks=[]), request("last", "POST")]
    steps[-1]["do"]["request"]["body"] = {
        "one": {"from_step": "a.b", "response_field": "c"},
        "two": {"from_step": "a", "response_field": "b.c"},
    }
    scenario = load(tmp_path, steps)
    prior = {"a.b": ports.NormalizedResponse(True, {"c": 1}, 200, None),
             "a": ports.NormalizedResponse(True, {"b.c": 2}, 200, None)}
    prepared, resolved = binding.prepare_step(scenario.steps[-1], scenario, prior)
    assert len(resolved) == 2
    assert prepared.request.body == {"one": 1, "two": 2}


def test_missing_grid_does_not_match_requested_filter(tmp_path):
    from refracto import grid
    scenario = load(tmp_path, [request()])
    assert grid.select(scenario)
    assert not grid.select(scenario, module="m")
    assert not grid.select(scenario, level="smoke")


def test_contract_null_response_reference_cannot_become_an_expected_null():
    from refracto.contract import store
    from refracto.declaration.model import Assertion, Binding, Expect, RequestTemplate, Scenario, Step, ValueRef
    scenario = Scenario("s", None, "reader", [], [], "", [
        Step("source", RequestTemplate("GET", "source"), Expect()),
        Step("target", RequestTemplate("GET", "target"),
             Expect(response=[Assertion("field_equals", {"field": "id", "value": ValueRef("bind", "id")})]),
             bind=[Binding("id", "source", "id")]),
    ])
    provider = store.Contract({
        ("source", "GET", "source"): store.EndpointShape(frozenset({"id"}), {"id": None}),
        ("target", "GET", "target"): store.EndpointShape(frozenset({"id"}), {"id": None}),
    })
    bindings = store.provider_binding_values(scenario, provider)
    assert bindings["target"] == {}
    assert store.diff(store.consumer_contract(scenario), provider, bound_values_by_step=bindings)


@pytest.mark.parametrize("prefix", [[], [request("earlier")],
    [{"id": "earlier", "do": "wait", "duration": 1000}]])
def test_backend_api_ui_preflight_rejects_entire_flow_before_effects(tmp_path, prefix):
    unsupported = request("unsupported")
    unsupported["expect"]["ui"] = [{"check": "visible", "anchor": "row"}]
    scenario = load(tmp_path, [*prefix, unsupported, request("blocked")])
    calls = []

    class Auth(FakeAuth):
        def session(self, role):
            calls.append("auth")
            return super().session(role)

    def resolve(scenario, step, template):
        calls.append("map")
        return ports.RequestSpec(template.method, template.path, body=template.body)

    api, recorder = FakeApi(), FakeRecorder()
    result = backend.run(scenario, auth=Auth(), api=api, state=None,
        recorder=recorder, resolve_request=resolve, normalizer=FakeNormalizer(),
        sleep=lambda duration: calls.append("wait"))
    assert [s.status for s in result.steps] == ["ERROR"] + ["BLOCKED"] * (len(scenario.steps) - 1)
    assert "direct API action with UI assertions" in result.steps[0].detail
    assert calls == []
    assert api.sent == []
    assert recorder.responses() == result.provider_recordings == []


def _run_live_projection(projection, scenario, api, recorder, normalizer, **kwargs):
    from refracto.projection import e2e
    implementation = backend if projection == "backend" else e2e
    if projection == "e2e":
        kwargs["ui"] = None
    return implementation.run(scenario, auth=FakeAuth(), api=api, state=None,
        recorder=recorder, normalizer=normalizer,
        resolve_request=lambda s, st, t: ports.RequestSpec(t.method, t.path, body=t.body),
        **kwargs)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("marker", ["fixture-sensitive-marker", "", False])
def test_live_api_rejects_any_non_none_fixture_marker_before_evaluation(tmp_path, projection, marker):
    class MarkedApi(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.mock_fixture_id = marker
            return response

    class CountingNormalizer(FakeNormalizer):
        calls = 0

        def normalize(self, response):
            self.calls += 1
            return super().normalize(response)

    scenario = load(tmp_path, [request("marked"), request("blocked")])
    api, recorder, normalizer = MarkedApi(), FakeRecorder(), CountingNormalizer()
    result = _run_live_projection(projection, scenario, api, recorder, normalizer)
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert "mock fixture marker" in result.steps[0].detail
    assert len(api.sent) == 1
    assert normalizer.calls == 0
    assert recorder.responses() == result.provider_recordings == []


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("marked_attempt", [0, 1])
def test_live_api_poll_rejects_fixture_on_first_or_later_attempt(tmp_path, projection, marked_attempt):
    class MarkedPollApi(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.json = {"success": True, "data": {"state": "pending"}}
            if len(self.sent) - 1 == marked_attempt:
                response.mock_fixture_id = "poll-fixture"
                response.json["data"]["state"] = "ready"
            return response

    class CountingNormalizer(FakeNormalizer):
        calls = 0

        def normalize(self, response):
            self.calls += 1
            return super().normalize(response)

    scenario = load(tmp_path, [request("poll", checks=[
        {"check": "field_equals", "field": "state", "value": "ready"}],
        poll={"on_timeout": "FAIL"}), request("blocked")])
    clock = [0]

    def sleep(duration):
        clock[0] += duration

    api, recorder, normalizer = MarkedPollApi(), FakeRecorder(), CountingNormalizer()
    result = _run_live_projection(projection, scenario, api, recorder, normalizer,
        now=lambda: clock[0], sleep=sleep, poll_config=runner.PollConfig(timeout=5, interval=1))
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert len(api.sent) == marked_attempt + 1
    assert normalizer.calls == marked_attempt
    assert len(recorder.responses()) == len(result.provider_recordings) == marked_attempt
    assert all(r.mock_fixture_id is None and not r.is_final for r in result.provider_recordings)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_missing_state_probe_degrades_without_echoing_resolved_secret(tmp_path, projection):
    from refracto.report import RunReport
    secret = "sensitive-bound-state-sentinel"
    target = request("target")
    target["expect"]["backend_state"] = [{"check": "span_attr", "span": "stored",
        "attr": "id", "op": "==", "value": {"from_step": "source", "response_field": "id"}}]
    scenario = load(tmp_path, [request("source", checks=[]), target])
    api = FakeApi({("GET", "records"): {"json": {"success": True, "data": {"id": secret}}}})
    result = _run_live_projection(projection, scenario, api, FakeRecorder(), FakeNormalizer())
    report = RunReport(scenario.id, [result])
    assert [s.status for s in result.steps] == ["COMPLETED", "PASSED"]
    assert result.status == report.status == "DEGRADED"
    assert list(result.steps[1].resolved_bindings.values()) == [secret]
    assert result.steps[1].skipped and report.degradations()
    assert "no StateProbe" in result.steps[1].skipped[0]
    assert secret not in str(report.degradations())
    for displayed in (result.steps[1], result, report):
        assert secret not in repr(displayed)
