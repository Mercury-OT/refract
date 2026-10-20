"""Contract replay distinguishes unexecuted work from observed mismatches."""
import copy
from dataclasses import replace

import pytest

from refracto.declaration.loader import _load_document
from refracto.projection import contract
from refracto.report import RunReport
from refracto.runner import PollConfig
from tests.fakes import FakeNormalizer
from tests.test_response_field_comparison import document, execute, request


def flow(*, selector=False, independent_failure=False, constraint=None):
    reference = {"from_step": "source", "response_field": "rows" if selector else "missing"}
    if selector:
        reference.update(matching={"code": "B"}, member_field="id")
    consumer = request("consume")
    if constraint == "numeric":
        consumer["expect"]["response"] = [
            {"check": "field_compare", "field": "count", "op": "<=", "value": reference}]
    elif constraint == "header":
        consumer["expect"]["response"] = [
            {"check": "header_equals", "header": "Location", "value": reference}]
    else:
        consumer["do"]["request"]["path"].append(reference)
    independent = request("independent", checks=[
        {"check": "field_equals", "field": "value", "value": "expected"}])
    scenario = _load_document(document(request("source"), consumer, independent))
    result, api = execute(scenario, {
        "source": {"rows": [{"code": "B", "id": 1}, {"code": "B", "id": 2}]},
        "independent": {"value": "wrong" if independent_failure else "expected"},
    })
    return scenario, result, api


@pytest.mark.parametrize("selector", [False, True])
@pytest.mark.parametrize("constraint", [None, "numeric", "header"])
def test_unexecuted_consumer_is_visible_blocked_not_an_endpoint_mismatch(selector, constraint):
    scenario, result, api = flow(selector=selector, constraint=constraint)
    assert [step.status for step in result.steps] == ["PASSED", "BLOCKED", "PASSED"]
    assert [sent.path for sent in api.sent] == ["source", "independent"]
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(),
                          execution_steps=result.steps)
    assert replay.status == "DEGRADED"
    assert [(step.step_id, step.status) for step in replay.steps if step.status == "BLOCKED"] == [
        ("consume", "BLOCKED")]
    assert not any(not check.ok for check in replay.checks)
    assert RunReport(scenario.id, [result, replay]).status == "DEGRADED"


@pytest.mark.parametrize("selector", [False, True])
def test_blocked_reference_does_not_hide_independent_observed_failure(selector):
    scenario, result, _ = flow(selector=selector, independent_failure=True)
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(),
                          execution_steps=result.steps)
    assert replay.status == "FAILED"
    assert any(check.step == "independent" and not check.ok for check in replay.checks)
    assert not any(check.step == "consume" for check in replay.checks)


def test_missing_execution_metadata_cannot_infer_blocked_from_missing_recording():
    scenario, result, _ = flow()
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer())
    assert replay.status == "FAILED"
    assert any(step.step_id == "consume" and step.status == "ERROR" for step in replay.steps)
    assert not any(step.status == "BLOCKED" for step in replay.steps)


def test_requestless_ui_action_stays_outside_backend_contract_obligations():
    scenario = _load_document(document(
        {"id": "open_page", "do": "open", "target": "records"},
        request("read")))
    result, _ = execute(scenario)
    assert result.steps[0].status == "NOT_APPLICABLE"
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(),
                          execution_steps=result.steps)
    assert replay.status == "PASSED"
    assert not any(check.step == "open_page" for check in replay.checks)


@pytest.mark.parametrize("tamper", ["missing", "duplicate", "unknown", "status", "blocked-user",
                                  "blocked-session", "blocked-check", "not-applicable",
                                  "missing-cause", "future-cause"])
def test_invalid_execution_provenance_is_not_a_license_to_omit_checks(tamper):
    scenario, result, _ = flow()
    steps = copy.deepcopy(result.steps)
    if tamper == "missing":
        steps.pop(1)
    elif tamper == "duplicate":
        steps.append(copy.deepcopy(steps[1]))
    elif tamper == "unknown":
        steps[1].step_id = "not-declared"
    elif tamper == "status":
        steps[1].status = "unknown-status"
    elif tamper == "blocked-user":
        steps[1].user = "other"
    elif tamper == "blocked-session":
        steps[1].session_generation = 0
    elif tamper == "blocked-check":
        steps[1].checks = copy.deepcopy(steps[0].checks)
    elif tamper == "not-applicable":
        steps[1].status = "NOT_APPLICABLE"
    elif tamper == "missing-cause":
        steps[1].blocked_by = []
    elif tamper == "future-cause":
        steps[1].blocked_by = ["independent"]
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=steps)
    assert replay.steps[0].status == "ERROR"
    assert replay.status == "FAILED"


def test_recording_for_a_claimed_unexecuted_step_is_a_provenance_error():
    scenario, result, _ = flow()
    consumer = scenario.steps[1]
    contradiction = replace(result.provider_recordings[0], step_id=consumer.id,
        template_path=consumer.request.path,
        request=replace(result.provider_recordings[0].request, path="consume/7"))
    replay = contract.run(scenario, [*result.provider_recordings, contradiction],
                          FakeNormalizer(), execution_steps=result.steps)
    assert replay.steps[0].status == "ERROR"
    assert "provenance" in replay.steps[0].detail


@pytest.mark.parametrize("keep_checks", [False, True])
def test_invented_blocked_label_cannot_erase_an_independent_observed_failure(keep_checks):
    scenario, result, _ = flow(independent_failure=True)
    steps = copy.deepcopy(result.steps)
    failed = steps[-1]
    failed.status = "BLOCKED"
    failed.session_generation = failed.response_origin = failed.trace_id = None
    failed.blocked_by = ["source"]
    if not keep_checks:
        failed.checks = []
    recordings = result.provider_recordings[:-1]
    replay = contract.run(scenario, recordings, FakeNormalizer(), execution_steps=steps)
    assert replay.steps[0].status == "ERROR"
    assert replay.status == "FAILED"


def test_declared_stop_retains_prior_real_mismatch_and_later_blocked():
    scenario = _load_document(document(
        request("first", checks=[{"check": "field_equals", "field": "value", "value": 1}],
                on_failure="stop"),
        request("later")))
    result, _ = execute(scenario, {"first": {"value": 2}})
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(),
                          execution_steps=result.steps)
    assert replay.status == "FAILED"
    assert any(check.step == "first" and not check.ok for check in replay.checks)
    assert not any(check.step == "later" for check in replay.checks)
    assert any(step.step_id == "later" and step.status == "BLOCKED" for step in replay.steps)


def test_impossible_recorded_selector_remains_error_but_independent_checks_survive():
    reference = {"from_step": "source", "response_field": "rows",
                 "matching": {"code": "B"}, "member_field": "id"}
    consumer = request("consume")
    consumer["do"]["request"]["path"].append(reference)
    scenario = _load_document(document(request("source"), consumer,
        request("independent", checks=[{"check": "field_equals", "field": "value", "value": "expected"}])))
    result, _ = execute(scenario, {"source": {"rows": [{"code": "B", "id": 1}]},
                                  "independent": {"value": "wrong"}})
    changed = copy.deepcopy(result.provider_recordings)
    changed[0].json["data"]["rows"].append({"code": "B", "id": 2})
    for provenance in (None, result.steps):
        replay = contract.run(scenario, changed, FakeNormalizer(), execution_steps=provenance)
        assert replay.steps[0].status == "ERROR"
        assert replay.steps[0].step_id == "consume"
        assert any(check.step == "independent" and not check.ok for check in replay.checks)
        assert replay.status == "FAILED"


@pytest.mark.parametrize("position,bad", [
    ("path", "."), ("path", ".."), ("path", ""), ("path", False),
    ("path", []), ("path", {}),
    ("query", []), ("query", {}), ("query", None),
    ("headers", False), ("headers", "bad\nvalue"), ("headers", None),
])
@pytest.mark.parametrize("independent_failure", [False, True])
def test_plain_response_reference_cannot_excuse_an_impossible_recorded_request(position, bad, independent_failure):
    from refracto import ports
    from refracto.query import wire_query
    from tests.fakes import FakeApi

    reference = {"from_step": "source", "response_field": "value"}
    consumer = request("consume")
    if position == "path":
        consumer["do"]["request"]["path"].append(reference)
    else:
        consumer["do"]["request"][position] = {"cursor" if position == "query" else "x-token": reference}
    scenario = _load_document(document(request("source"), consumer,
        request("independent", checks=[{"check": "field_equals", "field": "value", "value": "expected"}])))

    def resolver(scenario, step, template):
        return ports.RequestSpec(template.method, template.path, template.body,
            query=wire_query(template.query or {}), headers=dict(template.headers or {}))

    class Api(FakeApi):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.request_header_items = list(spec.headers.items())
            return response

    result, _ = execute(scenario, api=Api({
        ("GET", "source"): {"json": {"success": True, "data": {"value": "usable"}}},
        ("GET", "independent"): {"json": {"success": True, "data": {
            "value": "wrong" if independent_failure else "expected"}}},
    }), resolve_request=resolver)
    assert [step.status for step in result.steps] == [
        "PASSED", "PASSED", "FAILED" if independent_failure else "PASSED"]
    changed = copy.deepcopy(result.provider_recordings)
    changed[0].json["data"]["value"] = bad
    for provenance in (None, result.steps):
        baseline = contract.run(scenario, result.provider_recordings, FakeNormalizer(), execution_steps=provenance)
        assert baseline.status == ("FAILED" if independent_failure else "PASSED")
        replay = contract.run(scenario, changed, FakeNormalizer(), execution_steps=provenance)
        assert replay.steps[0].status == "ERROR"
        assert replay.steps[0].step_id == "consume"
        if independent_failure:
            assert any(check.step == "independent" and not check.ok for check in replay.checks)
        assert replay.status == "FAILED"


def test_poll_skip_still_requires_final_evidence_but_later_unexecuted_step_is_blocked():
    poll = request("source", checks=[{"check": "field_equals", "field": "ready", "value": True}],
                   poll={"on_timeout": "SKIP"})
    scenario = _load_document(document(poll, request("after")))
    clock = [0.0]
    result, _ = execute(scenario, {"source": {"ready": False}},
        poll_config=PollConfig(timeout=1, interval=1), now=lambda: clock[0],
        sleep=lambda delta: clock.__setitem__(0, clock[0] + delta))
    assert result.status == "DEGRADED"
    assert [step.status for step in result.steps] == ["SKIPPED", "BLOCKED"]
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(),
                          execution_steps=result.steps)
    assert replay.status == "FAILED"
    assert any(check.step == "source" and not check.ok for check in replay.checks)
    assert not any(check.step == "after" for check in replay.checks)
    assert any(step.step_id == "after" and step.status == "BLOCKED" for step in replay.steps)


def test_qualified_include_leaf_retains_its_own_blocked_identity(tmp_path):
    from tests.test_scenario_named_results import bundle, child, include
    from refracto.declaration.loader import load_scenario
    raw = child()
    raw["steps"].append(request("read_missing"))
    raw["steps"][-1]["do"]["request"]["path"].append(
        {"from_step": "create", "response_field": "missing"})
    path, _ = bundle(tmp_path, child_raw=raw, steps=[include(), request("independent")])
    scenario = load_scenario(path)
    result, _ = execute(scenario)
    replay = contract.run(scenario, result.provider_recordings, FakeNormalizer(),
                          execution_steps=result.steps)
    assert any(step.step_id == "setup/read_missing" and step.status == "BLOCKED" for step in replay.steps)
    assert not any(check.step == "setup/read_missing" for check in replay.checks)
