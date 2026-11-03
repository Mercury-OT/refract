"""Enter is an explicit primitive with checked, independently owned receipts.

These cooperative adapters model protocol claims; browser tests establish actual
selection, focus and trusted key delivery.
"""
import copy
from dataclasses import FrozenInstanceError, fields, replace
import json

import pytest
import yaml

from refracto import ports
from refracto.cli import main
from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import Step
from refracto.declaration.run_values import bind_run_values
from refracto.report import StepResult
from refracto.runner import Adapters, run_scenario
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_scenario_include import include, parent, write_bundle
from tests.ui_support import ScriptedUi, run


def press(**extra):
    return {"id": "search", "do": "press", "target": "records.search", "key": "Enter",
            "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}, **extra}


def document(*steps, parameters=None):
    return {"schema_version": 1, "scenario": "keyboard.example", "users": ["editor"],
            "parameters": parameters or {}, "steps": list(steps) or [press()]}


def load(*steps, parameters=None):
    return _load_document(document(*steps, parameters=parameters))


def click(**extra):
    item = press(id="later", do="click", **extra)
    item.pop("key")
    return item


class PressingUi(ScriptedUi):
    def supports_key_press(self, mode, key):
        return mode in {"mock", "live"} and key == "Enter"

    def perform_step(self, context, permit, **kwargs):
        result = super().perform_step(context, permit, **kwargs)
        if result.evidence is not None and permit.action == "press":
            receipt = ports.UiKeyPress(key=permit.key, target_matches=1, focused=True,
                                       keydown_count=1, keyup_count=1)
            result = replace(result, evidence=replace(result.evidence, key_press=receipt))
        if getattr(self, "press_mutate", None):
            result = self.press_mutate(result, permit)
        if self.evidence:
            self.evidence[-1] = result
        return result


def pressing_ui(count=1, **kwargs):
    return PressingUi(count=count, requests=[[] for _ in range(count)], **kwargs)


def test_literal_enter_survives_preparation_and_run_materialization():
    s = load()
    before = copy.deepcopy(s)
    bound, _ = bind_run_values(s)
    prepared, bindings = prepare_step(bound.steps[0], bound, {})
    assert prepared.key == "Enter" and prepared.action == "press"
    assert prepared.target == "records.search" and prepared.value is None
    assert bindings == {} and s == before
    assert "key" not in Step.__match_args__
    assert expansion_view(s)["steps"][0]["key"] == "Enter"


@pytest.mark.parametrize("key", [None, False, True, 1, "", "enter", "Return", "Esc",
    "Control+Enter", "Enter Enter", ["Enter"], {"from_parameter": "key"},
    {"from_step": "previous", "response_field": "key"}, {"concat": ["Enter"]}])
def test_other_or_dynamic_keys_are_rejected(key):
    with pytest.raises(DeclarationError):
        load(press(key=key), parameters={"key": "Enter"})


@pytest.mark.parametrize("missing", ["key", "target"])
def test_press_requires_both_literal_fields(missing):
    item = press()
    item.pop(missing)
    with pytest.raises(DeclarationError):
        load(item)


@pytest.mark.parametrize("extra", [{"value": None}, {"duration": 0}, {"object_id": None},
    {"poll": {}}, {"repeat": 1}, {"modifiers": []}, {"keys": ["Enter"]},
    {"target": ""}, {"target": {"from_parameter": "target"}}])
def test_press_rejects_extra_operation_fields_and_dynamic_target(extra):
    with pytest.raises(DeclarationError):
        load(press(**extra), parameters={"target": "records.search"})


@pytest.mark.parametrize("action,operation", [("open", {"target": "records.page"}),
    ("click", {"target": "records.search"}), ("fill", {"target": "records.search", "value": "x"}),
    ("wait", {"duration": 0}), ({"request": {"method": "GET", "path": ["records"]}}, {})])
def test_key_is_forbidden_on_all_existing_actions(action, operation):
    item = {"id": "other", "do": action, "key": "Enter", **operation}
    with pytest.raises(DeclarationError):
        load(item, press())


def test_press_delivery_does_not_count_as_a_scenario_assertion():
    with pytest.raises(DeclarationError, match="assertion"):
        load(press(expect={}))


def test_includes_keep_literal_key_and_existing_parameter_substitution(tmp_path, capsys):
    fill = {"id": "fill", "do": "fill", "target": "records.search",
            "value": {"from_parameter": "term"}}
    child = document(fill, press(), parameters={"term": "default"})
    child["scenario"] = "shared.create"
    calls = [include("first", **{"with": {"term": "alpha"}}),
             include("second", **{"with": {"term": "beta"}})]
    path, _ = write_bundle(tmp_path, parent(calls), child)
    s = load_scenario(path)
    assert [prepare_step(step, s, {})[0].value for step in s.steps[::2]] == ["alpha", "beta"]
    assert [prepare_step(step, s, {})[0].key for step in s.steps[1::2]] == ["Enter", "Enter"]
    assert main(["validate", str(path), "--expand"]) == 0
    expanded = json.loads(capsys.readouterr().out)
    assert [(item["id"], item["key"]) for item in expanded["steps"] if item["do"] == "press"] == [
        ("first/search", "Enter"), ("second/search", "Enter")]


@pytest.mark.parametrize("invalid", ["key-override", "dynamic-key", "nested"])
def test_include_does_not_expand_keyboard_grammar_or_depth(tmp_path, invalid):
    child = document()
    child["scenario"] = "shared.create"
    call = include()
    if invalid == "key-override":
        call["key"] = "Enter"
    elif invalid == "dynamic-key":
        child["parameters"] = {"key": "Enter"}
        child["steps"][0]["key"] = {"from_parameter": "key"}
        call["with"] = {"key": "Enter"}
    else:
        child["steps"].append(include("nested", "shared.other"))
    path, _ = write_bundle(tmp_path, parent([call]), child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_requestless_press_requires_delivery_and_owns_report_receipt(mode):
    ui = pressing_ui()
    result = run(load(), ui, mode=mode)
    assert result.steps[0].status == "PASSED"
    assert ui.permits[0].key == "Enter" and ui.permits[0].value is None
    receipt = result.steps[0].key_press
    assert receipt == ports.UiKeyPress(key="Enter", target_matches=1, focused=True,
                                      keydown_count=1, keyup_count=1)
    assert receipt is not ui.evidence[0].evidence.key_press
    object.__setattr__(ui.evidence[0].evidence.key_press, "keyup_count", 0)
    assert receipt.keyup_count == 1


def test_press_without_expectations_is_completed_with_receipt():
    ui = pressing_ui(count=2)
    result = run(load(press(expect={}), click()), ui)
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED"]
    assert result.steps[0].key_press is not None and result.steps[1].key_press is None


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("capability", [False, None, 0, 1, "true", [], {}])
def test_capability_requires_exact_true_before_context_or_action(mode, capability):
    ui = pressing_ui(count=2)
    ui.supports_key_press = lambda selected_mode, key: capability
    result = run(load(click(), press()), ui, mode=mode)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert ui.open_calls == 0 and ui.permits == []


def test_raising_capability_is_sanitized_before_any_context():
    ui = pressing_ui()
    def fail(mode, key):
        raise RuntimeError("private capability payload")
    ui.supports_key_press = fail
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"
    assert "private capability payload" not in result.steps[0].detail
    assert ui.open_calls == 0 and not ui.permits


def test_old_driver_keeps_ordinary_actions_and_opts_out_of_press():
    ordinary = ScriptedUi(count=1, requests=[[]])
    assert run(load(click()), ordinary).steps[0].status == "PASSED"
    old = ScriptedUi(count=1, requests=[[]])
    assert run(load(), old).steps[0].status == "ERROR"
    assert old.open_calls == 0 and not old.permits


@pytest.mark.parametrize("change", [{"key": None}, {"key": "Tab"}, {"key": ["Enter"]},
    {"target": None}, {"target": ""}, {"target": {}}, {"value": "input"},
    {"duration": 0}, {"object_id": "row"}, {"poll": object()}])
def test_direct_constructed_invalid_press_never_issues_a_permit(change):
    s = load()
    s.steps[0] = replace(s.steps[0], **change)
    ui = pressing_ui()
    assert run(s, ui).steps[0].status == "ERROR"
    assert ui.open_calls == 0 and not ui.permits


def test_direct_constructed_key_on_click_is_rejected():
    s = load(click())
    s.steps[0].key = "Enter"
    ui = pressing_ui()
    assert run(s, ui).steps[0].status == "ERROR"
    assert ui.open_calls == 0 and not ui.permits


@pytest.mark.parametrize("field,value", [("key", None), ("key", "Escape"), ("key", True),
    ("target_matches", 0), ("target_matches", 2), ("target_matches", True),
    ("focused", False), ("focused", 1), ("keydown_count", 0), ("keydown_count", 2),
    ("keydown_count", True), ("keyup_count", 0), ("keyup_count", 2), ("keyup_count", 1.0)])
def test_malformed_receipt_errors_and_blocks_following_action(field, value):
    ui = pressing_ui(count=2)
    ui.press_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        key_press=replace(result.evidence.key_press, **{field: value})))
    result = run(load(press(), click()), ui)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert result.steps[0].key_press is None and len(ui.permits) == 1


@pytest.mark.parametrize("receipt", [None, {}, "Enter"])
def test_missing_or_wrong_receipt_type_cannot_pass_without_a_request(receipt):
    ui = pressing_ui()
    ui.press_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, key_press=receipt))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_press_cannot_skip_without_delivery_evidence():
    ui = pressing_ui()
    ui.press_mutate = lambda result, permit: ports.UiActionResult(skip_reason="unavailable")
    assert run(load(), ui).steps[0].status == "ERROR"


def test_ordinary_action_must_not_claim_key_delivery():
    ui = pressing_ui()
    ui.press_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        key_press=ports.UiKeyPress(key="Enter", target_matches=1, focused=True,
                                  keydown_count=1, keyup_count=1)))
    assert run(load(click()), ui).steps[0].status == "ERROR"


@pytest.mark.parametrize("skip", [False, True])
def test_signed_key_mutation_cannot_pass_or_disguise_a_skip(skip):
    ui = pressing_ui()
    def mutate(result, permit):
        object.__setattr__(permit, "key", None)
        if skip:
            object.__setattr__(permit, "action", "click")
            return ports.UiActionResult(skip_reason="unavailable")
        return result
    ui.press_mutate = mutate
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"
    assert result.steps[0].detail == "action permit was modified"


@pytest.mark.parametrize("field,value", [("user", "other"), ("session_generation", 2),
    ("context_id", "other"), ("action_id", "other"), ("step_id", "other")])
def test_key_receipt_does_not_override_evidence_identity(field, value):
    ui = pressing_ui()
    ui.press_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, **{field: value}))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_replayed_press_evidence_cannot_serve_a_second_action():
    ui = pressing_ui(count=2)
    retained = []
    def replay(result, permit):
        if not retained:
            retained.append(result)
        return retained[0]
    ui.press_mutate = replay
    result = run(load(press(), press(id="again")), ui)
    assert [step.status for step in result.steps] == ["PASSED", "ERROR"]


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("case,status", [("correct", "PASSED"), ("wrong", "FAILED"),
                                        ("missing", "ERROR"), ("ambiguous", "ERROR")])
def test_existing_request_association_and_query_statuses_are_preserved(mode, case, status):
    request = ports.RequestSpec("GET", "records", query={"q": "wrong" if case == "wrong" else "alpha"})
    requests = [] if case == "missing" else [request, copy.deepcopy(request)] if case == "ambiguous" else [request]
    ui = PressingUi(count=2, requests=[requests, []])
    item = press(expect={"request": {"method": "GET", "path": ["records"], "query": {"q": "alpha"}},
                         "response": [{"check": "success"}]})
    result = run(load(item, click()), ui, mode=mode)
    assert result.steps[0].status == status
    assert result.steps[0].key_press is not None
    assert result.steps[1].status == ("BLOCKED" if status == "ERROR" else "PASSED")


def test_failed_query_honors_existing_stop_rule():
    ui = PressingUi(count=2, requests=[[ports.RequestSpec("GET", "records", query={"q": "wrong"})], []])
    item = press(on_failure="stop", expect={"request": {
        "method": "GET", "path": ["records"], "query": {"q": "alpha"}}})
    result = run(load(item, click()), ui)
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED"]


@pytest.mark.parametrize("mutator", ["later-action", "normalizer", "close"])
def test_report_receipt_is_owned_before_later_external_callbacks(mutator):
    requests = [[ports.RequestSpec("GET", "records")], []]
    ui = PressingUi(count=2, requests=requests)
    def corrupt():
        object.__setattr__(ui.evidence[0].evidence.key_press, "key", "private-mutation-payload")
    if mutator == "later-action":
        ui.press_mutate = lambda result, permit: (corrupt() or result) if permit.action == "click" else result
    elif mutator == "close":
        ui.close_stepwise = lambda context: corrupt()
    normalizer = FakeNormalizer()
    if mutator == "normalizer":
        ordinary = normalizer.normalize
        normalizer.normalize = lambda response: (corrupt() or ordinary(response))
    item = press(expect={"request": {"method": "GET", "path": ["records"]},
                         "response": [{"check": "success"}]})
    result = run(load(item, click()), ui, normalizer=normalizer)
    assert result.steps[0].status == "PASSED"
    assert result.steps[0].key_press.key == "Enter"
    assert ui.evidence[0].evidence.key_press.key == "private-mutation-payload"
    assert "private-mutation-payload" not in repr(result)


def test_receipt_and_key_model_compatibility_and_repr():
    ui = pressing_ui()
    result = run(load(), ui)
    permit, receipt = ui.permits[0], result.steps[0].key_press
    with pytest.raises(FrozenInstanceError):
        receipt.key = "Escape"
    assert ports.UiKeyPress.__match_args__ == () and ports.UiActionPermit.__match_args__ == ()
    assert replace(permit, key=None) != permit
    assert StepResult("s", "PASSED", key_press=receipt) == StepResult("s", "PASSED")
    assert "key_press" not in StepResult.__match_args__
    assert {item.name for item in fields(ports.UiKeyPress)} == {
        "key", "target_matches", "focused", "keydown_count", "keyup_count"}
    for cls, field in [(ports.UiActionEvidence, "key_press"), (StepResult, "key_press")]:
        descriptor = next(item for item in fields(cls) if item.name == field)
        assert not descriptor.repr and descriptor.metadata["sensitive"]
    object.__setattr__(receipt, "key", "private-key-payload")
    assert "private-key-payload" not in repr(receipt) + repr(result)


def test_runner_detects_press_as_requiring_a_ui_driver(tmp_path):
    path = tmp_path / "press.yaml"
    path.write_text(yaml.safe_dump(document(press(expect={"request": {
        "method": "GET", "path": ["records"]}}))), encoding="utf-8")
    adapters = Adapters(FakeAuth(), FakeApi(), None, None, FakeRecorder,
                        lambda action: ports.RequestSpec(action.method, action.path), FakeNormalizer())
    with pytest.raises(ValueError, match="no UiDriver"):
        run_scenario(path, adapters, projections=("e2e",))


def test_press_port_contains_only_operation_inputs():
    from tests.test_action_port_boundary import inspect_operation_data
    ui = pressing_ui()
    def inspect(result, permit):
        observed = inspect_operation_data(permit)
        assert observed["action"] == "press" and observed["key"] == "Enter"
        assert observed["target"] == "records.search" and observed["value"] is None
        assert not {"expect", "request", "parameters", "steps"} & set(observed)
        assert "expected-name-only" not in repr(observed)
        return result
    ui.press_mutate = inspect
    item = press(expect={"ui": [{"check": "objects_matching_count", "anchor": "rows",
                                "field": "name", "value": "expected-name-only", "count": 1}]})
    assert run(load(item), ui).steps[0].status == "FAILED"


def test_backend_and_contract_do_not_produce_key_delivery_receipts():
    from refracto.projection import backend, contract
    from tests.test_action_port_boundary import resolve
    item = press(expect={"request": {"method": "GET", "path": ["records"]},
                         "response": [{"check": "success"}]})
    s = load(item)
    result = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert result.steps[0].status == "PASSED" and result.steps[0].key_press is None
    assert "UI actions/checks are outside backend projection" in result.steps[0].not_checked
    compared = contract.run(s, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert compared.steps[0].status == "PASSED" and compared.steps[0].key_press is None
    assert compared.not_checked == ["search: key press is outside contract scope"]
    requestless = backend.run(load(), auth=FakeAuth(), api=FakeApi(), state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert requestless.steps[0].status == "NOT_APPLICABLE" and requestless.steps[0].key_press is None
