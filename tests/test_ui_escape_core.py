"""Escape declarations and operation receipts without invented browser evidence.

Cooperative fakes test protocol consistency; separate Chromium tests establish
real keyboard dispatch and the actual panel/input observations.
"""
import copy
from dataclasses import replace
import json

import pytest
import yaml

from refracto import ports
from refracto.cli import main
from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import Assertion, Expect, RequestTemplate
from refracto.declaration.run_values import bind_run_values
from refracto.projection import backend, contract
from refracto.runner import Adapters, run_flow, run_scenario
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_flow_ui import flow_path
from tests.test_scenario_include import include, parent, write_bundle
from tests.test_ui_press_core import PressingUi
from tests.test_users_sessions_core import Auth
from tests.ui_support import ScriptedUi, run


def escape(**extra):
    return {"id": "dismiss", "do": "press", "target": "records.search_input", "key": "Escape",
            "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}, **extra}


def document(*steps, parameters=None):
    return {"schema_version": 1, "scenario": "keyboard.dismiss", "users": ["editor"],
            "parameters": parameters or {}, "steps": list(steps) or [escape()]}


def load(*steps, parameters=None):
    return _load_document(document(*steps, parameters=parameters))


def click(**extra):
    item = escape(id="later", do="click", **extra)
    item.pop("key")
    return item


class KeyboardUi(PressingUi):
    def supports_key_press(self, mode, key):
        return mode in {"live", "mock"} and key in {"Enter", "Escape"}


def keyboard_ui(count=1, **kwargs):
    return KeyboardUi(count=count, requests=[[] for _ in range(count)], **kwargs)


def api_adapters(ui=None):
    return Adapters(FakeAuth(), FakeApi(), None, ui, FakeRecorder,
                    lambda action: ports.RequestSpec(action.method, action.path), FakeNormalizer())


def test_escape_survives_binding_preparation_and_expansion_without_mutation():
    scenario = load()
    before = copy.deepcopy(scenario)
    bound, _ = bind_run_values(scenario)
    prepared, bindings = prepare_step(bound.steps[0], bound, {})
    assert prepared.key == "Escape" and prepared.action == "press"
    assert prepared.request is None and bindings == {}
    assert scenario == before
    assert expansion_view(scenario)["steps"][0]["key"] == "Escape"


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_escape_uses_owned_real_key_receipt_and_no_request(mode):
    ui = keyboard_ui()
    result = run(load(), ui, mode=mode)
    assert result.status == "PASSED"
    receipt = result.steps[0].key_press
    assert receipt == ports.UiKeyPress(key="Escape", target_matches=1, focused=True,
                                      keydown_count=1, keyup_count=1)
    assert receipt is not ui.evidence[0].evidence.key_press
    object.__setattr__(ui.evidence[0].evidence.key_press, "keyup_count", 0)
    assert receipt.keyup_count == 1
    assert result.provider_recordings == []
    assert ui.open_calls == ui.close_calls == 1


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_all_distinct_keys_are_checked_before_authentication_or_context(mode):
    ui, auth, calls = keyboard_ui(3), Auth(), []
    def capability(selected_mode, key):
        calls.append((selected_mode, key))
        return key == "Enter"
    ui.supports_key_press = capability
    result = run(load(escape(id="submit", key="Enter"), escape(), escape(id="again")),
                 ui, mode=mode, auth=auth)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED", "BLOCKED"]
    assert calls == [(mode, "Enter"), (mode, "Escape")]
    assert auth.identified == auth.authenticated == []
    assert ui.open_calls == 0 and not ui.permits


@pytest.mark.parametrize("key", [None, False, True, 0, "", "escape", "Esc", "Tab", "Control+Escape",
    ["Escape"], {"from_parameter": "key"}, {"concat": ["Escape"]}])
def test_unknown_or_dynamic_keys_remain_invalid(key):
    with pytest.raises(DeclarationError):
        load(escape(key=key), parameters={"key": "Escape"})


@pytest.mark.parametrize("extra", [{"value": None}, {"duration": 0}, {"object_id": None},
    {"poll": {}}, {"repeat": 1}, {"modifiers": []}, {"keys": ["Escape"]},
    {"target": ""}, {"target": {"from_parameter": "target"}}])
def test_escape_keeps_existing_operation_field_limits(extra):
    with pytest.raises(DeclarationError):
        load(escape(**extra), parameters={"target": "records.search_input"})


@pytest.mark.parametrize("section,value", [
    ("request", {}), ("request", {"method": "GET", "path": ["records"]}),
    ("response", []), ("response", [{"check": "success"}]),
    ("backend_state", []), ("backend_state", [{"check": "span_exists", "span": "read"}]),
])
def test_escape_rejects_non_ui_expectations_even_when_empty(section, value):
    item = escape()
    item["expect"][section] = value
    with pytest.raises(DeclarationError, match="Escape supports only UI"):
        load(item)


def test_delivery_is_not_an_assertion_and_an_unchecked_step_can_complete():
    with pytest.raises(DeclarationError, match="assertion"):
        load(escape(expect={}))
    result = run(load(escape(expect={}), click()), keyboard_ui(2))
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED"]
    assert result.steps[0].key_press.key == "Escape"


def test_include_preserves_escape_key_and_qualified_id(tmp_path, capsys):
    child = document()
    child["scenario"] = "shared.create"
    path, _ = write_bundle(tmp_path, parent([include("first"), include("second")]), child)
    scenario = load_scenario(path)
    result = run(scenario, keyboard_ui(2))
    assert result.status == "PASSED"
    assert [step.step_id for step in result.steps] == ["first/dismiss", "second/dismiss"]
    assert all(step.key_press.key == "Escape" for step in result.steps)
    assert main(["validate", str(path), "--expand"]) == 0
    assert [step["key"] for step in json.loads(capsys.readouterr().out)["steps"]] == ["Escape"] * 2


@pytest.mark.parametrize("invalid", ["override", "nested", "request"])
def test_include_cannot_relax_escape_or_depth_boundaries(tmp_path, invalid):
    child, call = document(), include()
    child["scenario"] = "shared.create"
    if invalid == "override":
        call["key"] = "Enter"
    elif invalid == "nested":
        child["steps"].append(include("nested", "shared.other"))
    else:
        child["steps"][0]["expect"]["request"] = {"method": "GET", "path": ["records"]}
    path, _ = write_bundle(tmp_path, parent([call]), child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("capability", [False, None, 0, 1, "true", [], {}])
def test_escape_opt_in_requires_exact_true_before_auth_context_action(mode, capability):
    ui, auth = keyboard_ui(2), Auth()
    ui.supports_key_press = lambda selected_mode, key: capability
    result = run(load(click(), escape()), ui, mode=mode, auth=auth)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert not auth.identified and not auth.authenticated
    assert not ui.permits and ui.open_calls == 0


def test_raising_key_capability_is_sanitized_before_authentication():
    ui, auth = keyboard_ui(), Auth()
    def broken(mode, key):
        raise RuntimeError("PRIVATE_CAPABILITY_PAYLOAD")
    ui.supports_key_press = broken
    result = run(load(), ui, auth=auth)
    assert result.steps[0].status == "ERROR"
    assert "PRIVATE_CAPABILITY_PAYLOAD" not in result.steps[0].detail
    assert auth.identified == auth.authenticated == [] and ui.open_calls == 0


def test_legacy_and_enter_only_drivers_cannot_claim_escape_support():
    for ui in (ScriptedUi(count=1, requests=[[]]), PressingUi(count=1, requests=[[]])):
        assert run(load(), ui).steps[0].status == "ERROR"
        assert ui.open_calls == 0 and not ui.permits


def test_mixed_key_capability_is_queried_once_per_distinct_key_in_order():
    ui, calls = keyboard_ui(3), []
    ui.supports_key_press = lambda mode, key: calls.append((mode, key)) or True
    result = run(load(escape(), escape(id="submit", key="Enter"), escape(id="again")), ui)
    assert result.status == "PASSED"
    assert calls == [("live", "Escape"), ("live", "Enter")]
    assert [step.key_press.key for step in result.steps] == ["Escape", "Enter", "Escape"]


@pytest.mark.parametrize("change", [
    {"key": None}, {"key": "Tab"}, {"key": ["Escape"]}, {"target": None}, {"target": ""},
    {"target": {}}, {"value": "input"}, {"duration": 0}, {"object_id": "row"}, {"poll": object()},
    {"request_asserted": True}, {"request": RequestTemplate("GET", "records")},
    {"expect": Expect(response=[Assertion("success")])},
    {"expect": Expect(backend_state=[Assertion("span_exists", {"span": "read"})])},
])
def test_programmatic_escape_rejects_invalid_operations_before_authentication(change):
    scenario, ui, auth = load(), keyboard_ui(), Auth()
    scenario.steps[0] = replace(scenario.steps[0], **change)
    result = run(scenario, ui, auth=auth)
    assert result.steps[0].status == "ERROR"
    assert ui.open_calls == 0 and not ui.permits and not auth.identified


@pytest.mark.parametrize("field,value", [
    ("key", None), ("key", "Enter"), ("key", "escape"), ("key", True),
    ("target_matches", 0), ("target_matches", 2), ("target_matches", True), ("target_matches", 1.0),
    ("focused", False), ("focused", 1), ("keydown_count", 0), ("keydown_count", 2),
    ("keydown_count", True), ("keyup_count", 0), ("keyup_count", 2), ("keyup_count", 1.0),
])
def test_invalid_receipt_errors_and_blocks_later_action(field, value):
    ui = keyboard_ui(2)
    ui.press_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        key_press=replace(result.evidence.key_press, **{field: value})))
    result = run(load(escape(), click()), ui)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert result.steps[0].key_press is None and len(ui.permits) == 1


@pytest.mark.parametrize("receipt", [None, {}, "Escape"])
def test_missing_or_wrong_receipt_cannot_pass(receipt):
    ui = keyboard_ui()
    ui.press_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, key_press=receipt))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_derived_receipt_is_not_exact_protocol_type():
    class Derived(ports.UiKeyPress):
        pass
    ui = keyboard_ui()
    ui.press_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        key_press=Derived(key="Escape", target_matches=1, focused=True, keydown_count=1, keyup_count=1)))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_escape_cannot_skip_without_delivery():
    ui = keyboard_ui(2)
    ui.press_mutate = lambda result, permit: ports.UiActionResult(skip_reason="unavailable")
    assert [step.status for step in run(load(escape(), click()), ui).steps] == ["ERROR", "BLOCKED"]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_escape_cannot_claim_http_that_would_match_a_later_step(mode):
    ui = KeyboardUi(count=2, requests=[[ports.RequestSpec("GET", "records")], []])
    result = run(load(escape(), click()), ui, mode=mode)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert "associated request traffic" in result.steps[0].detail
    assert result.provider_recordings == []


def test_diagnostic_http_is_not_recorded_as_provider_evidence():
    ui = keyboard_ui()
    request = ports.RequestSpec("GET", "records")
    response = ports.RecordedResponse(200, {}, {"result": "ok"}, "", None, request)
    ui.press_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        diagnostic_outgoing=[request], diagnostic_recorded=[response]))
    result = run(load(), ui)
    assert result.status == "PASSED" and not result.provider_recordings


@pytest.mark.parametrize("field,value", [("execution_id", "stale"), ("user", "peer"),
    ("session_generation", 2), ("context_id", "stale"), ("action_id", "stale"),
    ("step_id", "stale"), ("mode", "other")])
def test_receipt_cannot_override_execution_identity(field, value):
    ui = keyboard_ui()
    ui.press_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, **{field: value}))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_key_is_signed_and_cannot_be_changed_after_issue():
    ui = keyboard_ui()
    def mutate(result, permit):
        object.__setattr__(permit, "key", "Enter")
        return result
    ui.press_mutate = mutate
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"
    assert result.steps[0].detail == "action permit was modified"


def test_replay_from_prior_step_or_run_is_rejected():
    retained, ui = [], keyboard_ui(2)
    def replay(result, permit):
        if not retained:
            retained.append(result)
        return retained[0]
    ui.press_mutate = replay
    assert [step.status for step in run(load(escape(), escape(id="again")), ui).steps] == ["PASSED", "ERROR"]
    fresh = keyboard_ui()
    fresh.press_mutate = replay
    assert run(load(), fresh).steps[0].status == "ERROR"


@pytest.mark.parametrize("stop", [False, True])
def test_observed_ui_failure_keeps_ordinary_continue_or_explicit_stop(stop):
    item = escape(expect={"ui": [{"check": "objects_matching_count", "anchor": "rows",
        "field": "name", "value": "wrong", "count": 1}]})
    if stop:
        item["on_failure"] = "stop"
    result = run(load(item, click()), keyboard_ui(2))
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED" if stop else "PASSED"]
    assert result.status == "FAILED" and result.steps[0].key_press.key == "Escape"


def test_adapter_receives_no_expectations_and_report_receipt_is_not_later_mutable():
    from tests.test_action_port_boundary import inspect_operation_data
    ui = keyboard_ui(2)
    def inspect(result, permit):
        observed = inspect_operation_data(permit)
        assert not {"expect", "request", "parameters", "steps"} & set(observed)
        assert "PRIVATE_EXPECTATION" not in repr(observed)
        if permit.action == "click":
            object.__setattr__(ui.evidence[0].evidence.key_press, "key", "PRIVATE_MUTATION")
        return result
    ui.press_mutate = inspect
    item = escape(expect={"ui": [{"check": "objects_matching_count", "anchor": "rows",
        "field": "name", "value": "PRIVATE_EXPECTATION", "count": 1}]})
    result = run(load(item, click()), ui)
    assert result.steps[0].status == "FAILED" and result.steps[0].key_press.key == "Escape"
    assert "PRIVATE_MUTATION" not in repr(result) + repr(ui.evidence[0].evidence.key_press)


@pytest.mark.parametrize("projections,status,domains", [
    (("backend",), "EMPTY", ["EMPTY"]),
    (("backend", "contract"), "EMPTY", ["EMPTY", "EMPTY"]),
    (("e2e",), "PASSED", ["PASSED"]),
    (("backend", "e2e"), "DEGRADED", ["EMPTY", "PASSED"]),
])
def test_escape_only_projections_do_not_claim_backend_or_contract_coverage(tmp_path, projections, status, domains):
    path = tmp_path / "escape.yaml"
    path.write_text(yaml.safe_dump(document()))
    adapters = api_adapters(keyboard_ui())
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == status and [domain.status for domain in report.domains] == domains
    assert adapters.api.sent == []
    for domain in report.domains:
        if domain.projection in {"backend", "contract"}:
            assert domain.checks == [] and not domain.provider_recordings


def test_mixed_backend_still_checks_later_request_without_keyboard_claim():
    item = click(expect={"request": {"method": "GET", "path": ["records"]},
                         "response": [{"check": "success"}]})
    scenario, adapters = load(escape(on_failure="stop"), item), api_adapters()
    result = backend.run(scenario, auth=adapters.auth, api=adapters.api, state=None,
        recorder=FakeRecorder(), resolve_request=adapters.resolve_request, normalizer=adapters.normalizer)
    assert [step.status for step in result.steps] == ["NOT_APPLICABLE", "PASSED"]
    assert result.steps[0].key_press is None and result.steps[0].not_checked
    compared = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert compared.status == "PASSED" and compared.not_checked == ["dismiss: key press is outside contract scope"]


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_flow_keeps_session_and_context_across_escape_then_enter(tmp_path, projection):
    first, second = document(), document(escape(key="Enter"))
    first["scenario"], second["scenario"] = "ui.dismiss", "ui.submit"
    path = flow_path(tmp_path, [first, second], mappings=[{"editor": "owner"}] * 2)
    ui = keyboard_ui(2)
    report = run_flow(path, api_adapters(ui), projections=(projection,),
                      mock_plan=[] if projection == "frontend" else None)
    assert report.status == "PASSED"
    assert ui.open_calls == ui.close_calls == 1
    assert len({permit.context_id for permit in ui.permits}) == 1
    assert all(permit.user == "owner" for permit in ui.permits)
    assert report.scenarios[0].domains[0].steps[0].key_press.key == "Escape"
    assert report.scenarios[1].domains[0].steps[0].key_press.key == "Enter"
