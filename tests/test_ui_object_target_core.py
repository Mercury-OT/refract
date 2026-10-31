"""Scoped UI selection stays typed, observable, and separate from expectations."""
import copy
from dataclasses import fields, replace

import pytest

from refracto import ports
from refracto.declaration.binding import InvalidDependency, MissingDependency, prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.impact import _references, _values
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.report import StepResult
from tests.test_scenario_include import include, parent, write_bundle
from tests.ui_support import ScriptedUi, run


def click(identity=22, **extra):
    return {"id": "edit", "do": "click", "target": "records.edit", "object_id": identity,
            "expect": {"ui": [{"check": "visible", "anchor": "rows"}]}, **extra}


def source(sid="create"):
    return {"id": sid, "do": "click", "target": "records.create", "expect": {
        "request": {"method": "POST", "path": ["items"]}, "response": [{"check": "success"}]}}


def document(*steps, parameters=None):
    return {"schema_version": 1, "scenario": "selection.example", "users": ["editor"],
            "parameters": parameters or {}, "steps": list(steps) or [click()]}


def load(*steps, parameters=None):
    return _load_document(document(*steps, parameters=parameters))


def norm(**values):
    return ports.NormalizedResponse(True, values, 200, None)


@pytest.mark.parametrize("identity", [0, -1, 22, "22", "record-22"])
@pytest.mark.parametrize("parameter", [False, True])
def test_selection_literal_and_parameter_keep_identity_type(identity, parameter):
    s = load(click({"from_parameter": "id"} if parameter else identity), parameters={"id": identity})
    prepared, _ = prepare_step(s.steps[0], s, {})
    assert type(prepared.object_id) is type(identity) and prepared.object_id == identity


@pytest.mark.parametrize("identity", [None, True, False, "", 1.0, [], {}, {"concat": ["id"]}])
@pytest.mark.parametrize("parameter", [False, True])
def test_known_bad_selection_identity_rejected(identity, parameter):
    if parameter and identity == {"concat": ["id"]}:
        # Only direct concat is forbidden; the existing parameter form works.
        s = load(click({"from_parameter": "id"}), parameters={"id": identity})
        assert prepare_step(s.steps[0], s, {})[0].object_id == "id"
        return
    with pytest.raises(DeclarationError):
        load(click({"from_parameter": "id"} if parameter else identity), parameters={"id": identity})


def test_selection_can_use_existing_composed_parameter():
    s = load(click({"from_parameter": "id"}), parameters={"id": {"concat": ["record-", "22"]}})
    assert prepare_step(s.steps[0], s, {})[0].object_id == "record-22"


@pytest.mark.parametrize("action,fields", [("open", {}), ("fill", {"value": "x"}),
    ("wait", {"duration": 1}), ({"request": {"method": "GET", "path": ["records"]}}, {})])
def test_selection_forbidden_on_other_actions(action, fields):
    item = click(do=action, **fields)
    if action == "wait" or isinstance(action, dict):
        item.pop("target")
        item["expect"] = {"response": [{"check": "success"}]} if isinstance(action, dict) else {}
    with pytest.raises(DeclarationError):
        load(item, source())


def test_selection_is_not_an_assertion_and_target_stays_literal():
    with pytest.raises(DeclarationError, match="assertion"):
        load(click(expect={}))
    with pytest.raises(DeclarationError):
        load(click(target={"from_parameter": "target"}), parameters={"target": "records.edit"})


@pytest.mark.parametrize("reference", [{"from_parameter": "missing"}, {"from_step": "later", "response_field": "id"},
    {"from_step": "edit", "response_field": "id"}, {"from_step": "create", "response_field": "id", "extra": 1}])
def test_selection_references_keep_strict_loader_rules(reference):
    with pytest.raises(DeclarationError):
        load(source(), click(reference))


@pytest.mark.parametrize("value", [False, True, "", 1.5, [], {}])
def test_invalid_response_identity_is_local_dependency_failure(value):
    s = load(source(), click({"from_step": "create", "response_field": "id"}))
    before = copy.deepcopy(s)
    with pytest.raises(InvalidDependency) as error:
        prepare_step(s.steps[1], s, {"create": norm(id=value)})
    assert error.value.sources == ["create"] and s == before


@pytest.mark.parametrize("payload,kind", [({}, MissingDependency), ({"id": None}, InvalidDependency)])
def test_missing_or_null_response_identity_has_no_default(payload, kind):
    s = load(source(), click({"from_step": "create", "response_field": "id"}))
    with pytest.raises(kind):
        prepare_step(s.steps[1], s, {"create": norm(**payload)})


@pytest.mark.parametrize("selector,payload", [({"key": "id"}, {"id": 22}),
    ({"matching": {"code": "selected"}, "member_field": "id"}, [{"id": 22, "code": "selected"}])])
def test_selection_uses_existing_response_member_references(selector, payload):
    s = load(source(), click({"from_step": "create", "response_field": "record", **selector}))
    assert prepare_step(s.steps[1], s, {"create": norm(record=payload)})[0].object_id == 22


def test_include_remaps_child_local_selection_and_repeated_instances(tmp_path):
    child = document(source(), click({"from_step": "create", "response_field": "id"}))
    child["scenario"] = "shared.create"
    path, _ = write_bundle(tmp_path, parent([include("first"), include("second")]), child)
    s = load_scenario(path)
    for index, scope in [(1, "first"), (3, "second")]:
        assert s.steps[index].bind[0].from_step == scope + "/create"
        assert prepare_step(s.steps[index], s, {scope + "/create": norm(id=index)})[0].object_id == index
    assert expansion_view(s)["steps"][1]["object_id"] == {
        "kind": "reference", "from_step": "first/create", "response_field": "id"}


@pytest.mark.parametrize("identity", [None, False, "", [], 1.0])
def test_bad_include_parameter_override_is_rejected(tmp_path, identity):
    child = document(click({"from_parameter": "id"}), parameters={"id": 22})
    child["scenario"] = "shared.create"
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"id": identity}})]), child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_named_result_selection_is_reviewed_and_attributed(tmp_path):
    child = document(source())
    child["scenario"] = "shared.create"
    child["results"] = {"record_id": {"from_step": "create", "response_field": "id"}}
    consumer = click({"from_step": "setup", "result": "record_id"})
    path, _ = write_bundle(tmp_path, parent([include(), consumer]), child)
    s = load_scenario(path)
    assert prepare_step(s.steps[1], s, {"setup/create": norm(id=22)})[0].object_id == 22
    refs = [ref for location, value in _values(consumer, 1) for ref in _references(value, location)]
    assert refs == [("setup", "record_id", "/steps/1/object_id")]


def test_selection_cannot_override_include_behavior(tmp_path):
    path, _ = write_bundle(tmp_path, parent([include(object_id=22)]))
    with pytest.raises(DeclarationError):
        load_scenario(path)


class SelectingUi(ScriptedUi):
    def supports_object_targeting(self, mode):
        return mode in {"live", "mock"}

    def perform_step(self, context, permit, **kwargs):
        result = super().perform_step(context, permit, **kwargs)
        if result.evidence is not None and permit.object_id is not None:
            receipt = ports.UiObjectSelection(object_id=permit.object_id, object_matches=1, control_matches=1)
            result = replace(result, evidence=replace(result.evidence, object_selection=receipt))
        if getattr(self, "selection_mutate", None):
            result = self.selection_mutate(result, permit)
        self.evidence[-1] = result
        return result


def selected_ui(count=1, **kwargs):
    return SelectingUi(count=count, requests=[[] for _ in range(count)], **kwargs)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_scoped_requestless_click_requires_and_preserves_selection_receipt(mode):
    ui = selected_ui()
    result = run(load(), ui, mode=mode)
    assert result.steps[0].status == "PASSED"
    receipt = result.steps[0].object_selection
    assert receipt.object_id == 22 and receipt.object_matches == receipt.control_matches == 1
    assert receipt is not ui.evidence[0].evidence.object_selection
    object.__setattr__(ui.evidence[0].evidence.object_selection, "object_id", 999)
    assert receipt.object_id == 22


@pytest.mark.parametrize("capability", [False, None, 1, "true"])
def test_capability_must_be_exact_true_before_any_context_or_business_action(capability):
    ui = selected_ui(count=2)
    ui.supports_object_targeting = lambda mode: capability
    result = run(load(source(), click()), ui)
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert ui.permits == [] and ui.open_calls == 0


def test_old_adapter_remains_usable_unscoped_and_rejects_scoped():
    ui = ScriptedUi(count=1, requests=[[]])
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR" and not ui.permits and ui.open_calls == 0
    item = click()
    item.pop("object_id")
    assert run(load(item), ScriptedUi(count=1, requests=[[]])).steps[0].status == "PASSED"


@pytest.mark.parametrize("changes", [None, {}, {"object_id": False}, {"object_id": True}, {"object_id": "22"},
    {"object_id": 23}, {"object_matches": 0}, {"object_matches": 2}, {"object_matches": True},
    {"control_matches": 0}, {"control_matches": 2}, {"control_matches": True}])
def test_invalid_or_missing_selection_receipt_never_passes_without_traffic(changes):
    ui = selected_ui(count=2)
    def mutate(result, permit):
        receipt = None if changes is None else {} if changes == {} else replace(result.evidence.object_selection, **changes)
        return replace(result, evidence=replace(result.evidence, object_selection=receipt))
    ui.selection_mutate = mutate
    result = run(load(click(), click(id="later")), ui)
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert len(ui.permits) == 1


def test_bool_int_receipt_confusion_is_rejected():
    ui = selected_ui()
    ui.selection_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        object_selection=replace(result.evidence.object_selection, object_id=False)))
    assert run(load(click(0)), ui).steps[0].status == "ERROR"


def test_unscoped_action_cannot_claim_object_selection():
    item = click()
    item.pop("object_id")
    ui = selected_ui()
    ui.selection_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        object_selection=ports.UiObjectSelection(object_id=22, object_matches=1, control_matches=1)))
    assert run(load(item), ui).steps[0].status == "ERROR"


def test_mutating_permit_object_id_invalidates_signature():
    ui = selected_ui()
    def mutate(result, permit):
        object.__setattr__(permit, "object_id", 23)
        return replace(result, evidence=replace(result.evidence,
            object_selection=ports.UiObjectSelection(object_id=23, object_matches=1, control_matches=1)))
    ui.selection_mutate = mutate
    assert run(load(), ui).steps[0].status == "ERROR"


@pytest.mark.parametrize("bad_id", [None, False, [], ""])
def test_bad_runtime_identity_blocks_only_dependent_action(bad_id):
    ui = SelectingUi(count=2, requests=[[ports.RequestSpec("POST", "items")], []],
                     payloads=[{"success": True, "data": {"id": bad_id}}, {}])
    ordinary = click(id="independent")
    ordinary.pop("object_id")
    result = run(load(source(), click({"from_step": "create", "response_field": "id"}), ordinary), ui)
    assert [s.status for s in result.steps] == ["PASSED", "BLOCKED", "PASSED"]
    assert [p.step_id for p in ui.permits] == ["create", "independent"]


def test_selection_payloads_are_sensitive_and_omitted_from_default_repr():
    secret = "private-selection-sentinel"
    s = load(click(secret))
    ui = selected_ui()
    result = run(s, ui)
    receipt = result.steps[0].object_selection
    assert secret not in repr(s) + repr(ui.permits[0]) + repr(receipt) + repr(result)
    for cls, name in [(type(s.steps[0]), "object_id"), (ports.UiActionPermit, "object_id"),
                      (ports.UiActionEvidence, "object_selection"), (StepResult, "object_selection")]:
        assert next(f for f in fields(cls) if f.name == name).metadata["sensitive"] is True


def test_scoped_adapter_skip_cannot_replace_missing_selection_evidence():
    ui = selected_ui()
    ui.terminal = (0, "skip")
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"


@pytest.mark.parametrize("field", ["object_matches", "control_matches"])
@pytest.mark.parametrize("count", [None, "1", 1.0, False, -1])
def test_selection_counts_require_exact_integer_one(field, count):
    ui = selected_ui()
    ui.selection_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence,
        object_selection=replace(result.evidence.object_selection, **{field: count})))
    assert run(load(), ui).steps[0].status == "ERROR"


@pytest.mark.parametrize("field,value", [("user", "other"), ("session_generation", 99),
    ("context_id", "other"), ("step_id", "other"), ("action_id", "other"), ("execution_id", "other")])
def test_selection_does_not_replace_existing_execution_identity_checks(field, value):
    ui = selected_ui()
    ui.selection_mutate = lambda result, permit: replace(result, evidence=replace(result.evidence, **{field: value}))
    assert run(load(), ui).steps[0].status == "ERROR"


def test_selection_receipt_is_protected_before_normalizer_callback():
    from tests.fakes import FakeNormalizer
    ui = SelectingUi(count=1)
    class MutatingNormalizer(FakeNormalizer):
        def normalize(self, recorded):
            object.__setattr__(ui.evidence[0].evidence.object_selection, "object_id", 999)
            return super().normalize(recorded)
    item = click(expect={"request": {"method": "POST", "path": ["items"]},
                         "response": [{"check": "success"}]})
    result = run(load(item), ui, normalizer=MutatingNormalizer())
    assert result.steps[0].status == "PASSED"
    assert result.steps[0].object_selection.object_id == 22
    assert ui.evidence[0].evidence.object_selection.object_id == 999


def test_selection_receipt_is_retained_if_later_response_check_fails():
    ui = SelectingUi(count=1)
    item = click(expect={"request": {"method": "POST", "path": ["items"]},
                         "response": [{"check": "failure"}]})
    result = run(load(item), ui)
    assert result.steps[0].status == "FAILED"
    assert result.steps[0].object_selection.object_id == 22


def test_backend_and_contract_never_claim_ui_selection_was_checked():
    from refracto.projection import backend, contract
    from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
    from tests.test_action_port_boundary import resolve
    item = click(expect={"request": {"method": "POST", "path": ["items"]},
                         "response": [{"check": "success"}]})
    s = load(item)
    result = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert result.steps[0].status == "PASSED"
    assert result.steps[0].object_selection is None
    assert "object_id selection is outside backend projection" in result.steps[0].not_checked
    compared = contract.run(s, result.provider_recordings, FakeNormalizer(), execution_steps=result.steps)
    assert compared.steps[0].status == "PASSED"
    assert any("object_id selection is outside contract scope" in text for text in compared.not_checked)
    requestless = backend.run(load(), auth=FakeAuth(), api=FakeApi(), state=None,
        recorder=FakeRecorder(), resolve_request=resolve, normalizer=FakeNormalizer())
    assert requestless.steps[0].status == "NOT_APPLICABLE"
    assert "object_id selection is outside backend projection" in requestless.steps[0].not_checked


def test_scoped_action_port_still_receives_only_operation_data():
    from tests.test_action_port_boundary import inspect_operation_data
    ui = selected_ui()
    def inspect(result, permit):
        observed = inspect_operation_data(permit)
        assert observed["object_id"] == 22 and observed["target"] == "records.edit"
        assert "expect" not in observed and "request" not in observed
        return result
    ui.selection_mutate = inspect
    assert run(load(), ui).steps[0].status == "PASSED"


def test_mutated_scoped_permit_cannot_be_disguised_as_an_unscoped_skip():
    ui = selected_ui()
    def mutate(result, permit):
        object.__setattr__(permit, "object_id", None)
        return ports.UiActionResult(skip_reason="not available")
    ui.selection_mutate = mutate
    result = run(load(), ui)
    assert result.steps[0].status == "ERROR"
    assert result.steps[0].detail == "action permit was modified"


@pytest.mark.parametrize("observed", [22, False])
def test_response_reference_passed_into_include_retains_binding_and_failure_source(tmp_path, observed):
    child = document(click({"from_parameter": "id"}), parameters={"id": 1})
    child["scenario"] = "shared.create"
    root = parent([source(), include(**{"with": {"id": {"from_step": "create", "response_field": "id"}}})])
    path, _ = write_bundle(tmp_path, root, child)
    s = load_scenario(path)
    assert s.steps[1].bind[0].from_step == "create"
    if type(observed) is int:
        assert prepare_step(s.steps[1], s, {"create": norm(id=observed)})[0].object_id == observed
    else:
        with pytest.raises(InvalidDependency) as failure:
            prepare_step(s.steps[1], s, {"create": norm(id=observed)})
        assert failure.value.sources == ["create"]
