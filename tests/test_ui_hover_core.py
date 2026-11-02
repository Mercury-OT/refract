"""Bounded hover protocol claims, declaration shape and projection honesty.

Cooperative fake adapters exercise core invariants; separate browser tests
establish actual pointer delivery and DOM observation.
"""
import copy
from dataclasses import FrozenInstanceError, fields, replace
import json
from pathlib import Path
import re

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
from refracto.report import StepResult
from refracto.runner import Adapters, run_flow, run_scenario
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.test_flow_ui import flow_path
from tests.test_scenario_include import include, parent, write_bundle
from tests.test_users_sessions_core import Auth
from tests.ui_support import ScriptedUi, run


def hover(**extra):
    return {"id": "reveal", "do": "hover", "target": "records.menu_trigger",
            "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}, **extra}


def document(*steps, parameters=None):
    return {"schema_version": 1, "scenario": "hover.example", "users": ["editor"],
            "parameters": parameters or {}, "steps": list(steps) or [hover()]}


def load(*steps, parameters=None):
    return _load_document(document(*steps, parameters=parameters))


def click(**extra):
    return hover(id="later", do="click", **extra)


class HoveringUi(ScriptedUi):
    def supports_hover(self, mode):
        return mode in {"mock", "live"}

    def perform_step(self, context, permit, **kwargs):
        result = super().perform_step(context, permit, **kwargs)
        if result.evidence is not None and permit.action == "hover":
            receipt = ports.UiHover(target_matches=1, pointer_on_target=True)
            result = replace(result, evidence=replace(result.evidence, hover=receipt))
        if getattr(self, "hover_mutate", None):
            result = self.hover_mutate(result, permit)
        if self.evidence:
            self.evidence[-1] = result
        return result


def hovering_ui(count=1, **kwargs):
    return HoveringUi(count=count, requests=[[] for _ in range(count)], **kwargs)


def api_adapters(ui=None):
    return Adapters(FakeAuth(), FakeApi(), None, ui, FakeRecorder,
                    lambda action: ports.RequestSpec(action.method, action.path), FakeNormalizer())


def test_literal_hover_survives_binding_and_expansion_without_new_values():
    scenario = load()
    before = copy.deepcopy(scenario)
    bound, _ = bind_run_values(scenario)
    prepared, bindings = prepare_step(bound.steps[0], bound, {})
    assert prepared.action == "hover" and prepared.target == "records.menu_trigger"
    assert prepared.value is prepared.key is prepared.object_id is prepared.request is None
    assert bindings == {} and scenario == before
    expanded = expansion_view(scenario)["steps"][0]
    assert expanded["do"] == "hover" and expanded["target"] == "records.menu_trigger"
    assert not {"key", "value", "object_id", "duration"} & set(expanded)


def test_documented_hover_fragment_loads_with_its_declared_parameter():
    text = (Path(__file__).resolve().parents[1] / "SCENARIO.md").read_text()
    blocks = [block for block in re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
              if "do: hover" in block]
    assert len(blocks) == 1
    scenario = load(*yaml.safe_load(blocks[0]), parameters={"menu_text": "Archived records"})
    assert scenario.steps[0].action == "hover" and scenario.steps[0].request is None


@pytest.mark.parametrize("extra", [
    {"value": None}, {"key": None}, {"key": "Enter"}, {"duration": 0},
    {"object_id": None}, {"poll": {}}, {"repeat": 1}, {"force": True},
    {"position": {"x": 1, "y": 1}}, {"target": ""}, {"target": None},
    {"target": ["records.menu_trigger"]},
    {"target": {"from_parameter": "target"}}, {"target": {"concat": ["menu"]}},
])
def test_hover_rejects_unapproved_operation_fields_and_dynamic_target(extra):
    with pytest.raises(DeclarationError):
        load(hover(**extra), parameters={"target": "records.menu_trigger"})


def test_hover_requires_target():
    item = hover()
    del item["target"]
    with pytest.raises(DeclarationError):
        load(item)


@pytest.mark.parametrize("section,value", [
    ("request", {}), ("request", {"method": "GET", "path": ["records"]}),
    ("response", []), ("response", [{"check": "success"}]),
    ("backend_state", []), ("backend_state", [{"check": "span_exists", "span": "read"}]),
])
def test_hover_rejects_non_ui_expectations_even_when_empty(section, value):
    item = hover()
    item["expect"][section] = value
    with pytest.raises(DeclarationError, match="hover supports only UI"):
        load(item)


def test_hover_delivery_is_not_an_assertion_but_multiple_ui_checks_are_allowed():
    with pytest.raises(DeclarationError, match="assertion"):
        load(hover(expect={}))
    item = hover(expect={"ui": [
        {"check": "visible", "anchor": "rows"},
        {"check": "objects_matching_count", "anchor": "rows", "field": "name",
         "value": "alpha", "count": 1},
    ]})
    result = run(load(hover(expect={}), item | {"id": "checked"}), hovering_ui(2))
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED"]
    assert len(result.steps[1].checks) == 2


def test_include_preserves_hover_parameter_checks_and_qualified_identity(tmp_path, capsys):
    item = hover(expect={"ui": [{"check": "objects_matching_count", "anchor": "rows",
        "field": "name", "value": {"from_parameter": "name"}, "count": 1}]})
    child = document(item, parameters={"name": "default"})
    child["scenario"] = "shared.create"
    path, _ = write_bundle(tmp_path, parent([
        include("first", **{"with": {"name": "alpha"}}),
        include("second", **{"with": {"name": "alpha"}}),
    ]), child)
    scenario = load_scenario(path)
    result = run(scenario, hovering_ui(2))
    assert result.status == "PASSED"
    assert [step.step_id for step in result.steps] == ["first/reveal", "second/reveal"]
    assert all(step.hover is not None for step in result.steps)
    assert main(["validate", str(path), "--expand"]) == 0
    expanded = json.loads(capsys.readouterr().out)
    assert all(step["do"] == "hover" for step in expanded["steps"])


@pytest.mark.parametrize("invalid", ["override", "nested", "request"])
def test_include_cannot_relax_hover_or_depth_boundaries(tmp_path, invalid):
    child, call = document(), include()
    child["scenario"] = "shared.create"
    if invalid == "override":
        call["target"] = "other.menu"
    elif invalid == "nested":
        child["steps"].append(include("nested", "shared.other"))
    else:
        child["steps"][0]["expect"]["request"] = {"method": "GET", "path": ["records"]}
    path, _ = write_bundle(tmp_path, parent([call]), child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_hover_requires_pointer_receipt_and_owns_report_copy(mode):
    ui = hovering_ui()
    result = run(load(), ui, mode=mode)
    assert result.steps[0].status == "PASSED"
    receipt = result.steps[0].hover
    assert receipt == ports.UiHover(target_matches=1, pointer_on_target=True)
    assert receipt is not ui.evidence[0].evidence.hover
    object.__setattr__(ui.evidence[0].evidence.hover, "pointer_on_target", False)
    assert receipt.pointer_on_target is True
    assert ui.open_calls == ui.close_calls == 1


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("capability", [False, None, 0, 1, "true", [], {}])
def test_hover_capability_requires_exact_true_before_auth_context_or_action(mode, capability):
    ui, auth = hovering_ui(2), Auth()
    ui.supports_hover = lambda selected_mode: capability
    result = run(load(click(), hover()), ui, mode=mode, auth=auth)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert ui.open_calls == ui.close_calls == 0 and not ui.permits
    assert auth.identified == auth.authenticated == []


def test_raising_hover_capability_is_sanitized_before_context():
    ui = hovering_ui()
    def fail(mode):
        raise RuntimeError("private capability payload")
    ui.supports_hover = fail
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"
    assert "private capability payload" not in result.steps[0].detail
    assert ui.open_calls == 0 and not ui.permits


def test_old_driver_still_supports_ordinary_actions_and_opts_out_of_hover():
    ordinary = ScriptedUi(count=1, requests=[[]])
    assert run(load(click()), ordinary).steps[0].status == "PASSED"
    old = ScriptedUi(count=1, requests=[[]])
    assert run(load(), old).steps[0].status == "ERROR"
    assert old.open_calls == 0 and not old.permits


@pytest.mark.parametrize("change", [
    {"target": None}, {"target": ""}, {"target": {}}, {"value": "input"}, {"key": "Enter"},
    {"duration": 0}, {"object_id": "row"}, {"poll": object()}, {"request_asserted": True},
    {"request": RequestTemplate("GET", "records")},
    {"expect": Expect(response=[Assertion("success")])},
    {"expect": Expect(backend_state=[Assertion("span_exists", {"span": "read"})])},
])
def test_direct_invalid_hover_never_issues_permit(change):
    scenario = load()
    scenario.steps[0] = replace(scenario.steps[0], **change)
    ui = hovering_ui()
    assert run(scenario, ui).steps[0].status == "ERROR"
    assert ui.open_calls == 0 and not ui.permits


@pytest.mark.parametrize("field,value", [
    ("target_matches", 0), ("target_matches", 2), ("target_matches", True),
    ("target_matches", 1.0), ("target_matches", "1"),
    ("pointer_on_target", False), ("pointer_on_target", 1), ("pointer_on_target", "true"),
])
def test_malformed_pointer_receipt_errors_and_blocks_next_action(field, value):
    ui = hovering_ui(2)
    ui.hover_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        hover=replace(result.evidence.hover, **{field: value})))
    result = run(load(hover(), click()), ui)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert result.steps[0].hover is None and len(ui.permits) == 1


@pytest.mark.parametrize("receipt", [None, {}, "hover", ports.UiKeyPress(
    key="Enter", target_matches=1, focused=True, keydown_count=1, keyup_count=1)])
def test_absent_or_wrong_pointer_receipt_type_cannot_pass(receipt):
    ui = hovering_ui()
    ui.hover_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, hover=receipt))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_receipt_subclass_is_not_a_strict_protocol_value():
    class Derived(ports.UiHover):
        pass
    ui = hovering_ui()
    ui.hover_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        hover=Derived(target_matches=1, pointer_on_target=True)))
    assert run(load(), ui).steps[0].status == "ERROR"


@pytest.mark.parametrize("other_receipt", [
    {"key_press": ports.UiKeyPress(key="Enter", target_matches=1, focused=True,
                                  keydown_count=1, keyup_count=1)},
    {"object_selection": ports.UiObjectSelection(object_id="row", object_matches=1, control_matches=1)},
])
def test_hover_cannot_claim_an_extra_operation_receipt(other_receipt):
    ui = hovering_ui()
    ui.hover_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, **other_receipt))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_hover_cannot_skip_without_pointer_delivery():
    ui = hovering_ui()
    ui.hover_mutate = lambda result, permit: ports.UiActionResult(skip_reason="unavailable")
    assert run(load(), ui).steps[0].status == "ERROR"


def test_other_action_cannot_claim_hover_receipt():
    ui = hovering_ui()
    ui.hover_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        hover=ports.UiHover(target_matches=1, pointer_on_target=True)))
    assert run(load(click()), ui).steps[0].status == "ERROR"


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_hover_cannot_claim_associated_http_even_when_it_matches_later_request(mode):
    ui = HoveringUi(count=2, requests=[[ports.RequestSpec("GET", "records")], []])
    result = run(load(hover(), click()), ui, mode=mode)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert "associated request traffic" in result.steps[0].detail
    assert not result.provider_recordings


def test_hover_background_request_diagnostics_do_not_become_provider_evidence():
    ui = hovering_ui()
    background = ports.RequestSpec("GET", "background")
    response = ports.RecordedResponse(200, {}, {"status": "ok"}, "", None, background)
    ui.hover_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        diagnostic_outgoing=[background], diagnostic_recorded=[response]))
    result = run(load(), ui)
    assert result.status == "PASSED" and result.provider_recordings == []


@pytest.mark.parametrize("skip", [False, True])
def test_signed_hover_mutation_cannot_pass_or_disguise_a_skip(skip):
    ui = hovering_ui()
    def mutate(result, permit):
        object.__setattr__(permit, "action", "click")
        return ports.UiActionResult(skip_reason="unavailable") if skip else result
    ui.hover_mutate = mutate
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"
    assert result.steps[0].detail == "action permit was modified"


@pytest.mark.parametrize("field,value", [
    ("execution_id", "other"), ("user", "other"), ("session_generation", 2),
    ("context_id", "other"), ("action_id", "other"), ("step_id", "other"), ("mode", "other"),
])
def test_hover_receipt_does_not_override_execution_identity(field, value):
    ui = hovering_ui()
    ui.hover_mutate = lambda result, permit: replace(result,
        evidence=replace(result.evidence, **{field: value}))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_replayed_hover_evidence_cannot_serve_another_action_or_run():
    ui, retained = hovering_ui(2), []
    def replay(result, permit):
        if not retained:
            retained.append(result)
        return retained[0]
    ui.hover_mutate = replay
    result = run(load(hover(), hover(id="again")), ui)
    assert [step.status for step in result.steps] == ["PASSED", "ERROR"]
    fresh = hovering_ui()
    fresh.hover_mutate = replay
    assert run(load(), fresh).steps[0].status == "ERROR"


@pytest.mark.parametrize("stop", [False, True])
def test_observed_ui_mismatch_is_failed_and_uses_existing_continuation(stop):
    item = hover(expect={"ui": [{"check": "objects_matching_count", "anchor": "rows",
        "field": "name", "value": "wrong", "count": 1}]})
    if stop:
        item["on_failure"] = "stop"
    result = run(load(item, click()), hovering_ui(2))
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED" if stop else "PASSED"]
    assert result.steps[0].hover is not None
    assert result.status == "FAILED"


@pytest.mark.parametrize("mutator", ["later-action", "close"])
def test_report_receipt_is_owned_before_later_external_callbacks(mutator):
    ui = hovering_ui(2)
    def corrupt():
        object.__setattr__(ui.evidence[0].evidence.hover, "pointer_on_target", "private-payload")
    if mutator == "later-action":
        ui.hover_mutate = lambda result, permit: (corrupt() or result) if permit.action == "click" else result
    else:
        ui.close_stepwise = lambda context: corrupt()
    result = run(load(hover(), click()), ui)
    assert result.steps[0].hover.pointer_on_target is True
    assert ui.evidence[0].evidence.hover.pointer_on_target == "private-payload"
    assert "private-payload" not in repr(result) + repr(ui.evidence[0].evidence.hover)


def test_hover_model_is_frozen_keyword_only_and_hidden_from_default_report_repr():
    result = run(load(), hovering_ui())
    receipt = result.steps[0].hover
    with pytest.raises(FrozenInstanceError):
        receipt.pointer_on_target = False
    assert ports.UiHover.__match_args__ == ()
    assert "hover" not in StepResult.__match_args__
    assert StepResult("s", "PASSED", hover=receipt) == StepResult("s", "PASSED")
    assert {field.name for field in fields(ports.UiHover)} == {"target_matches", "pointer_on_target"}
    for cls in (ports.UiActionEvidence, StepResult):
        descriptor = next(field for field in fields(cls) if field.name == "hover")
        assert not descriptor.repr and descriptor.metadata["sensitive"]


def test_hover_port_receives_operations_only_not_ui_expectations():
    from tests.test_action_port_boundary import inspect_operation_data
    ui = hovering_ui()
    def inspect(result, permit):
        observed = inspect_operation_data(permit)
        assert observed["action"] == "hover" and observed["target"] == "records.menu_trigger"
        assert not {"expect", "request", "parameters", "steps"} & set(observed)
        assert "expected-name-only" not in repr(observed)
        return result
    ui.hover_mutate = inspect
    item = hover(expect={"ui": [{"check": "objects_matching_count", "anchor": "rows",
                               "field": "name", "value": "expected-name-only", "count": 1}]})
    assert run(load(item), ui).steps[0].status == "FAILED"


def test_mixed_backend_skips_hover_and_checks_declared_later_request():
    item = click(expect={"request": {"method": "GET", "path": ["records"]},
                         "response": [{"check": "success"}]})
    scenario = load(hover(on_failure="stop"), item)
    adapters = api_adapters()
    result = backend.run(scenario, auth=adapters.auth, api=adapters.api, state=None,
        recorder=FakeRecorder(), resolve_request=adapters.resolve_request, normalizer=adapters.normalizer)
    assert [step.status for step in result.steps] == ["NOT_APPLICABLE", "PASSED"]
    assert result.status == "PASSED" and len(adapters.api.sent) == 1
    assert result.steps[0].hover is None and result.steps[0].not_checked
    compared = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert compared.status == "PASSED"
    assert compared.not_checked == ["reveal: hover is outside contract scope"]


@pytest.mark.parametrize("projections,status,domains", [
    (("backend",), "EMPTY", ["EMPTY"]),
    (("backend", "contract"), "EMPTY", ["EMPTY", "EMPTY"]),
    (("e2e",), "PASSED", ["PASSED"]),
    (("backend", "e2e"), "DEGRADED", ["EMPTY", "PASSED"]),
])
def test_hover_only_projection_and_run_aggregation_remain_honest(tmp_path, projections, status, domains):
    path = tmp_path / "hover.yaml"
    path.write_text(yaml.safe_dump(document()))
    adapters = api_adapters(hovering_ui())
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == status
    assert [domain.status for domain in report.domains] == domains
    assert adapters.api.sent == []
    for domain in report.domains:
        if domain.projection in {"backend", "contract"}:
            assert domain.checks == [] and not domain.provider_recordings


def test_runner_needs_ui_even_for_hover_without_own_assertion(tmp_path):
    path = tmp_path / "hover.yaml"
    path.write_text(yaml.safe_dump(document(hover(expect={}), {
        "id": "read", "do": {"request": {"method": "GET", "path": ["records"]}},
        "expect": {"response": [{"check": "success"}]},
    })))
    with pytest.raises(ValueError, match="no UiDriver"):
        run_scenario(path, api_adapters(), projections=("e2e",))


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_flow_schedules_hover_with_same_session_and_context(tmp_path, projection):
    first, second = document(hover()), document(click())
    first["scenario"], second["scenario"] = "ui.reveal", "ui.click"
    path = flow_path(tmp_path, [first, second], mappings=[{"editor": "owner"}] * 2)
    ui = hovering_ui(2)
    report = run_flow(path, api_adapters(ui), projections=(projection,),
                      mock_plan=[] if projection == "frontend" else None)
    assert report.status == "PASSED"
    assert ui.open_calls == ui.close_calls == 1
    assert len({permit.context_id for permit in ui.permits}) == 1
    assert all(permit.user == "owner" for permit in ui.permits)
    assert report.scenarios[0].domains[0].steps[0].hover is not None
    assert report.scenarios[1].domains[0].steps[0].hover is None
