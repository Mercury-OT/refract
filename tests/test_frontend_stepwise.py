"""Primitive frontend: explicit mock plans, evidence identity and no hidden flow."""
import copy
import dataclasses
import pytest
from refracto import ports
from refracto.declaration.model import Assertion, Binding, Expect, Step, ValueRef
from refracto.projection import frontend
from refracto.report import DomainResult, RunReport
from tests.fakes import FakeAuth, FakeNormalizer, FakeUi
from tests.ui_support import ScriptedUi, response, run, scenario


def test_single_and_multiple_steps_use_same_primitive_capability():
    for count in (1, 2):
        ui = ScriptedUi(count)
        result = run(scenario(count=count), ui, mode="mock")
        assert result.status == "PASSED"
        assert len(ui.permits) == count
        assert ui.open_calls == ui.close_calls == 1
        assert all(context is ui.contexts[0] for context in ui.contexts)
        assert len(result.mock_consumption) == count
        assert result.not_checked == ["mock fixtures are not live backend evidence"]
        assert result.provider_recordings == []


def test_no_mock_synthesis_or_live_fallback():
    ui = ScriptedUi()
    result = frontend.run(scenario(), ui=ui, normalizer=FakeNormalizer())
    assert result.steps[0].status == "ERROR"
    assert ui.open_calls == 0
    result = run(scenario(), ui, mode="mock", mock_plan=[])
    assert result.steps[0].status == "ERROR"


def test_requestless_actions_complete_without_invented_checks():
    s = scenario(count=1)
    s.steps.insert(0, Step("fill", None, Expect(), action="fill", target="name", value="alpha"))
    ui = ScriptedUi(requests=[[], [ports.RequestSpec("POST", "items", {"name": "alpha"})]])
    result = run(s, ui, mode="mock")
    assert [r.status for r in result.steps] == ["COMPLETED", "PASSED"]
    assert result.steps[0].checks == []
    assert [p.action for p in ui.permits] == ["fill", "click"]


def test_ordered_repeated_endpoint_fixtures_and_response_references():
    ui = ScriptedUi()
    result = run(scenario(references=True), ui, mode="mock")
    assert result.status == "PASSED"
    assert result.steps[1].resolved_bindings == {"previous": "1"}
    assert ui.permits[1].value == "1"
    assert [x["fixture_id"] for x in result.mock_consumption] == ["f0-0", "f1-0"]
    assert result.steps[1].resolved_bindings is not ui.permits[1].resolved_bindings


@pytest.mark.parametrize("terminal, expected", [("error", "ERROR"), ("skip", "SKIPPED"), ("failed", "FAILED")])
def test_terminal_state_blocks_and_preserves_successful_binding(terminal, expected):
    ui = ScriptedUi(3, terminal=(1, terminal))
    if terminal == "failed":
        ui.renders[1] = {}
    result = run(scenario(count=3, references=True), ui, mode="mock")
    assert [r.status for r in result.steps] == ["PASSED", expected, "PASSED" if terminal == "failed" else "BLOCKED"]
    assert result.steps[1].resolved_bindings == {"previous": "1"}
    assert result.steps[2].resolved_bindings == ({"previous": "1"} if terminal == "failed" else {})
    assert ui.close_calls == 1


def test_atomic_resolution_does_not_expose_partial_results():
    s = scenario(references=True)
    s.steps[1].bind.append(Binding("missing", "s0", "absent"))
    ui = ScriptedUi()
    result = run(s, ui, mode="mock")
    assert result.steps[1].status == "BLOCKED"
    assert result.steps[1].resolved_bindings == {}
    assert len(ui.permits) == 1


@pytest.mark.parametrize("value", [False, 0, "", {"nested": []}])
def test_reference_values_preserve_type_and_only_top_mapping_is_copied(value):
    ui = ScriptedUi(payloads=[response({"id": value}), response()])
    result = run(scenario(references=True), ui, mode="mock")
    assert result.status == "PASSED"
    assert type(result.steps[1].resolved_bindings["previous"]) is type(value)
    assert result.steps[1].resolved_bindings["previous"] == value
    if type(value) is dict:
        assert result.steps[1].resolved_bindings["previous"] is ui.permits[1].resolved_bindings["previous"]


@pytest.mark.parametrize("where, field, value", [
    ("action", "execution_id", "stale"), ("action", "action_id", "wrong"),
    ("action", "step_id", "wrong"), ("action", "mode", "live"),
    ("action", "permit_token", "wrong"), ("traffic", "execution_id", "stale"),
    ("traffic", "action_id", "wrong"), ("traffic", "step_id", "wrong"),
    ("traffic", "mode", "live"), ("traffic", "request_id", False),
    ("traffic", "permit_token", "wrong"), ("response", "step_id", "wrong"),
    ("response", "attempt_index", False), ("response", "attempt_index", True),
    ("response", "is_final", 1), ("response", "trace_id", "wrong"),
    ("response", "actual_path", ""), ("response", "actual_path", None),
    ("response", "request_id", "swapped"),
])
def test_each_protocol_identity_is_strict(where, field, value):
    def mutate(index, result, permit):
        evidence = result.evidence
        if where == "action":
            evidence = dataclasses.replace(evidence, **{field: value})
        else:
            traffic = evidence.traffic[0]
            if where == "traffic":
                traffic = dataclasses.replace(traffic, **{field: value})
            else:
                traffic = dataclasses.replace(traffic, response=dataclasses.replace(traffic.response, **{field: value}))
            evidence = dataclasses.replace(evidence, traffic=[traffic])
        return ports.UiActionResult(evidence=evidence)
    ui = ScriptedUi(mutate=mutate)
    result = run(scenario(), ui, mode="mock")
    assert [r.status for r in result.steps] == ["ERROR", "BLOCKED"]


@pytest.mark.parametrize("actual, expected", [(False, 0), (True, 1), (0, False), (1, True)])
def test_nested_mock_and_request_type_confusion_cannot_pass(actual, expected):
    ui = ScriptedUi(requests=[[ports.RequestSpec("POST", "items", {"name": actual})]] * 2)
    s = scenario()
    s.steps[0].request.body = {"name": expected}
    result = run(s, ui, mode="mock")
    assert [r.status for r in result.steps] == ["FAILED", "FAILED"]
    def change(i, result, permit):
        e = result.evidence
        t = e.traffic[0]
        r = dataclasses.replace(t.response, json=response({"id": [actual]}))
        return ports.UiActionResult(evidence=dataclasses.replace(e, traffic=[dataclasses.replace(t, response=r)], mock_recordings=[r]))
    ui = ScriptedUi(payloads=[response({"id": [expected]})] * 2, mutate=change)
    assert run(scenario(), ui, mode="mock").steps[0].status == "ERROR"


def test_request_body_subset_allows_additional_transport_fields_but_not_array_growth():
    s = scenario(count=1)
    s.steps[0].request.body = {"nested": {"x": 1}, "array": [{"a": False}]}
    request = ports.RequestSpec("POST", "items", {"nested": {"x": 1, "extra": 2}, "array": [{"a": False, "b": 3}], "transport": 7})
    ui = ScriptedUi(1, requests=[[request]])
    assert run(s, ui, mode="mock").status == "PASSED"
    request.body["array"].append({"a": False})
    assert run(s, ScriptedUi(1, requests=[[request]]), mode="mock").status == "FAILED"


def test_same_run_and_cross_run_replay_fail():
    captured = []
    def replay(index, result, permit):
        if not captured:
            captured.append(result)
            return result
        return captured[0]
    ui = ScriptedUi(mutate=replay)
    assert run(scenario(), ui, mode="mock").steps[1].status == "ERROR"
    assert run(scenario(), ScriptedUi(mutate=replay), mode="mock").steps[0].status == "ERROR"


def test_zero_and_multiple_requests_are_supported_but_target_must_be_unique():
    s = scenario(count=1)
    req = ports.RequestSpec("POST", "items", {"name": "alpha"})
    ui = ScriptedUi(1, requests=[[req, ports.RequestSpec("GET", "refresh")]])
    assert run(s, ui, mode="mock").status == "PASSED"
    assert run(s, ScriptedUi(1, requests=[[req, req]]), mode="mock").steps[0].status == "ERROR"
    assert run(s, ScriptedUi(1, requests=[[]]), mode="mock").steps[0].status == "ERROR"


@pytest.mark.parametrize("close_error", [False, True])
def test_context_closes_once_on_every_opened_path(close_error):
    class Driver(ScriptedUi):
        def close_stepwise(self, context):
            super().close_stepwise(context)
            if close_error:
                raise RuntimeError("close error")
    ui = Driver()
    result = run(scenario(), ui, mode="mock")
    assert ui.close_calls == 1
    assert result.steps[-1].status == ("ERROR" if close_error else "PASSED")


def test_sensitive_payloads_hidden_through_report_and_permits():
    secret = "sensitive-sentinel"
    ui = ScriptedUi(payloads=[response({"id": secret}), response()])
    domain = run(scenario(references=True), ui, mode="mock")
    for obj in [*ui.permits, *ui.evidence, domain, RunReport("x", [domain])]:
        assert secret not in repr(obj)
    assert ports.UiActionPermit.__match_args__ == ()
    assert dataclasses.fields(ports.UiActionPermit)[-1].metadata["sensitive"]


def test_action_result_requires_evidence_xor_skip():
    with pytest.raises(ValueError):
        ports.UiActionResult()
    with pytest.raises(ValueError):
        ports.UiActionResult(evidence=object(), skip_reason="skip")


def test_frontend_rejects_direct_api_and_requestless_state_before_context():
    for kind in ("api", "state"):
        s, ui = scenario(), ScriptedUi()
        if kind == "api":
            s.steps[0].action = "request"
        else:
            s.steps[0].request = None
            s.steps[0].expect.backend_state = [Assertion("span_exists", {"span": "x"})]
        assert run(s, ui, mode="mock").steps[0].status == "ERROR"
        assert ui.open_calls == 0


def test_wait_is_core_milliseconds_and_never_an_extra_ui_action():
    s = scenario(count=1)
    s.steps.insert(0, Step("wait", None, Expect(), action="wait", duration=25))
    ui, delays = ScriptedUi(1), []
    result = run(s, ui, mode="mock", sleep=delays.append)
    assert delays == [0.025]
    assert [r.status for r in result.steps] == ["COMPLETED", "PASSED"]
    assert len(ui.permits) == 1


def test_pure_ui_scenario_needs_no_fictitious_request_or_response():
    s = scenario(count=2)
    for step in s.steps:
        step.request = None
        step.expect.response = []
        step.request_asserted = False
    s.steps[0].expect.frontend = []
    result = run(s, ScriptedUi(requests=[[], []]), mode="mock", mock_plan=[])
    assert [r.status for r in result.steps] == ["COMPLETED", "PASSED"]
    assert {c.point for c in result.checks} == {"frontend"}
    assert result.mock_consumption == []


def test_loaded_response_reference_drives_action_path_body_and_assertion(tmp_path):
    from refracto.declaration.loader import load_scenario
    path = tmp_path / "references.yaml"
    path.write_text("""schema_version: 1
scenario: refs.ui
actor: editor
steps:
  - id: create
    do: click
    target: create
    expect:
      request: {method: POST, path: [items]}
      response: [{check: success}]
  - id: fill
    do: fill
    target: name
    value: {from_step: create, response_field: id}
  - id: update
    do: click
    target: update
    expect:
      request:
        method: PUT
        path: [items, {from_step: create, response_field: id}]
        body: {name: {from_step: create, response_field: id}}
      ui:
        - check: objects_matching_count
          anchor: rows
          field: name
          value: {from_step: create, response_field: id}
          count: 1
""", encoding="utf-8")
    ui = ScriptedUi(3, payloads=[response({"id": "a/b"}), response(), response()],
        requests=[[ports.RequestSpec("POST", "items")], [], [ports.RequestSpec("PUT", "items/a%2Fb", {"name": "a/b"})]],
        renders=[{}, {}, {"rows": {"identified": [], "anonymous": [{"fields": {"name": "a/b"}}]}}])
    result = run(load_scenario(path), ui, mode="mock")
    assert result.status == "PASSED"
    assert ui.permits[1].value == "a/b"
    assert result.steps[1].status == "COMPLETED"
    assert list(result.steps[2].resolved_bindings.values()) == ["a/b"]
