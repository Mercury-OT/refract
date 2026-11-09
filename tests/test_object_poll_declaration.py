"""Object waiting is opt-in, single-selection and validated before actions."""
from copy import deepcopy
from dataclasses import replace

import pytest

from refracto.declaration.binding import InvalidDependency, prepare_step
from refracto.declaration.expansion import expansion_view, flow_expansion_view
from refracto.declaration.flows import load_flow
from refracto.declaration.loader import DeclarationError, _load_document, load_scenario
from refracto.declaration.model import PollPolicy
from tests.test_flow_runtime import flow_path, scenario as flow_scenario
from tests.test_object_state_declaration import check, document, norm, request
from tests.test_scenario_include import write_bundle


def step(*, assertions=None, **changes):
    value = request(assertions=assertions)
    value["object_poll"] = {"on_timeout": "FAIL"}
    value.update(changes)
    return value


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_explicit_requests_keep_original_method_and_one_optional_policy(method):
    raw = step()
    raw["do"]["request"]["method"] = method
    scenario = _load_document(document(raw))
    assert scenario.steps[0].request.method == method
    assert scenario.steps[0].object_poll == PollPolicy("FAIL")
    assert scenario.steps[0].poll is None
    assert expansion_view(scenario)["steps"][0]["object_poll"] == {"on_timeout": "FAIL"}


@pytest.mark.parametrize("policy", [None, True, "FAIL", [], {}, {"on_timeout": "SKIP"},
    {"on_timeout": "fail"}, {"on_timeout": True}, {"on_timeout": 0},
    {"on_timeout": {"from_parameter": "policy"}}, {"on_timeout": "FAIL", "timeout": 2},
    {"on_timeout": "FAIL", "interval": 1}, {"on_timeout": "FAIL", "unknown": 1}])
def test_policy_is_exact_explicit_fail_only(policy):
    with pytest.raises(DeclarationError):
        _load_document(document(step(object_poll=policy)))


@pytest.mark.parametrize("action", ["open", "click", "fill", "press"])
def test_request_associated_ui_action_can_wait_without_repeating_action(action):
    raw = step(do=action, target="records.action")
    raw["expect"]["request"] = {"method": "POST", "path": ["records"]}
    if action == "fill":
        raw["value"] = "Example"
    if action == "press":
        raw["key"] = "Enter"
    assert _load_document(document(raw)).steps[0].object_poll is not None


@pytest.mark.parametrize("action", ["open", "click", "fill", "press", "hover", "wait"])
def test_requestless_steps_cannot_claim_object_poll(action):
    raw = step(do=action)
    if action == "wait":
        raw["duration"] = 0
    else:
        raw["target"] = "records.action"
    if action == "fill":
        raw["value"] = "Example"
    if action == "press":
        raw["key"] = "Escape"
    with pytest.raises(DeclarationError):
        _load_document(document(raw))


@pytest.mark.parametrize("assertions", [[], [{"check": "span_exists", "span": "removed"}],
    [check(), {"check": "span_exists", "span": "removed"}]])
def test_policy_needs_object_checks_and_cannot_mix_span_waits(assertions):
    raw = step(assertions=assertions)
    raw["expect"]["response"] = [{"check": "success"}]
    with pytest.raises(DeclarationError, match="only object-state"):
        _load_document(document(raw))


def test_existing_get_poll_cannot_be_combined_with_object_poll():
    raw = step(poll={"on_timeout": "FAIL"})
    raw["expect"]["response"] = [{"check": "success"}]
    with pytest.raises(DeclarationError, match="combined"):
        _load_document(document(raw))


@pytest.mark.parametrize("location", ["top", "expect", "do", "assertion"])
def test_policy_in_wrong_location_is_rejected(location):
    raw = document(request())
    target = {"top": raw, "expect": raw["steps"][0]["expect"],
              "do": raw["steps"][0]["do"],
              "assertion": raw["steps"][0]["expect"]["backend_state"][0]}[location]
    target["object_poll"] = {"on_timeout": "FAIL"}
    with pytest.raises(DeclarationError):
        _load_document(raw)


@pytest.mark.parametrize("second", [23, "22", False, None])
def test_known_different_or_invalid_ids_are_rejected(second):
    raw = step(assertions=[check(), check(field="code", id={"from_parameter": "other"})])
    with pytest.raises(DeclarationError):
        _load_document(document(raw, parameters={"record_id": 22, "other": second}))


def test_different_business_objects_are_rejected_even_with_unknown_id():
    ref = {"from_step": "create", "response_field": "id"}
    raw = step(assertions=[check(id=deepcopy(ref)), check(object="document", id=deepcopy(ref))])
    with pytest.raises(DeclarationError, match="one business object"):
        _load_document(document(request("create", []), raw))


def test_different_refs_to_same_typed_identity_are_valid_and_snapshot_shared():
    raw = step(assertions=[check(), check(field="code", id={"from_parameter": "other"})])
    scenario = _load_document(document(raw, parameters={"record_id": 22, "other": 22}))
    prepared, _ = prepare_step(scenario.steps[0], scenario, {})
    assert [a.params["id"] for a in prepared.expect.backend_state] == [22, 22]


@pytest.mark.parametrize("second", [23, "22"])
def test_runtime_disagreement_preserves_dependency_and_blocks_before_action(second):
    refs = [{"from_step": "create", "response_field": key} for key in ("id", "other")]
    scenario = _load_document(document(request("create", []), step(assertions=[
        check(id=refs[0]), check(field="code", id=refs[1])])))
    before = deepcopy(scenario.steps[1])
    with pytest.raises(InvalidDependency, match="one exact typed ID") as error:
        prepare_step(scenario.steps[1], scenario, {"create": norm(id=22, other=second)})
    assert error.value.sources == ["create"] and scenario.steps[1] == before


def test_include_keeps_policy_and_checks_override_selector_consistency(tmp_path):
    child = document(step(assertions=[check(), check(field="code", id={"from_parameter": "other"})]),
                     parameters={"record_id": 22, "other": 22})
    child["scenario"] = "shared.wait"
    call = {"id": "shared", "do": {"include": "shared.wait"}}
    path, _ = write_bundle(tmp_path, document(call), child)
    loaded = load_scenario(path)
    assert loaded.steps[0].id == "shared/read"
    assert loaded.steps[0].object_poll == PollPolicy("FAIL")
    assert expansion_view(loaded)["steps"][0]["object_poll"] == {"on_timeout": "FAIL"}
    call["with"] = {"other": "22"}
    path, _ = write_bundle(tmp_path, document(call), child)
    with pytest.raises(DeclarationError, match="one exact typed ID"):
        load_scenario(path)


def test_include_call_itself_cannot_gain_poll_policy(tmp_path):
    child = document(step())
    child["scenario"] = "shared.wait"
    call = {"id": "shared", "do": {"include": "shared.wait"}, "object_poll": {"on_timeout": "FAIL"}}
    path, _ = write_bundle(tmp_path, document(call), child)
    with pytest.raises(DeclarationError):
        load_scenario(path)


def test_flow_retains_policy_in_expanded_leaves(tmp_path):
    child = flow_scenario("records.wait", [step()], parameters={"record_id": 22})
    flow = load_flow(flow_path(tmp_path, [child]))
    assert flow.scenario.steps[0].id == "n0/read"
    assert flow.scenario.steps[0].object_poll == PollPolicy("FAIL")
    assert flow_expansion_view(flow)["execution"]["steps"][0]["object_poll"] == {"on_timeout": "FAIL"}


def test_default_steps_stay_one_shot_without_policy():
    scenario = _load_document(document(request()))
    assert scenario.steps[0].object_poll is None
    assert "object_poll" not in expansion_view(scenario)["steps"][0]
