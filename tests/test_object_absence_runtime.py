"""Absence is one exact lookup after a real response, with honest failures."""
from copy import deepcopy
from dataclasses import fields, replace

import pytest

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.projection import contract
from refracto.report import BLOCKED, DEGRADED, EMPTY, ERROR, FAILED, PASSED, SKIPPED
from refracto.runner import PollConfig, run_flow, run_scenario
from tests.fakes import FakeApi, FakeNormalizer
from tests.test_flow_runtime import flow_path, scenario as flow_scenario
from tests.test_object_state_declaration import document, request
from tests.test_object_state_runtime import Probe, adapters, Clock, SequenceApi
from tests import test_object_state_runtime as shared
from tests.test_scenario_include import write_bundle
from tests.ui_support import ScriptedUi


def absent(*, identity=22, object_name="record"):
    return {"check": "object_absent", "object": object_name, "id": identity}


def api_step(name="remove", *, checks=None, response=True):
    return shared.api_step(name, checks=[absent()] if checks is None else checks, response=response)


def write(tmp_path, steps, *, parameters=None, **options):
    steps, parameters = deepcopy(steps), deepcopy(parameters or {})
    for step in steps:
        for assertion in step.get("expect", {}).get("backend_state", []):
            if assertion["check"] == "object_absent" and type(assertion["id"]) is not dict:
                name = f"absence_id_{len(parameters)}"
                parameters[name] = assertion["id"]
                assertion["id"] = {"from_parameter": name}
    return shared.write(tmp_path, steps, parameters=parameters, **options)


def facts(selector, *, count=0, **changes):
    return replace(ports.ObjectStateFacts(query=selector, source="memory-records", complete=True,
        objects=[ports.ObservedObject(id=selector.id, fields={}) for _ in range(count)]), **changes)


def run(tmp_path, steps=None, *, probe=None, projection="backend", users=None, parameters=None, **options):
    path = write(tmp_path, [api_step()] if steps is None else steps, users=users, parameters=parameters)
    return run_scenario(path, adapters(probe, **options), projections=(projection,))


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("count,status", [(0, PASSED), (1, FAILED), (2, ERROR)])
def test_complete_lookup_distinguishes_zero_one_and_ambiguous_matches(tmp_path, projection, count, status):
    probe = Probe(lambda q: facts(q, count=count))
    report = run(tmp_path, probe=probe, projection=projection)
    sr = report.domains[0].steps[0]
    assert sr.status == status
    assert report.status == (FAILED if status == ERROR else status)
    assert len(probe.queries) == len(sr.state_observations) == 1
    assert probe.queries[0].fields == ()
    checks = [c for c in sr.checks if c.check == "object_absent"]
    assert len(checks) == (0 if count > 1 else 1)
    if checks:
        assert checks[0].ok is (count == 0)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_absence_only_never_uses_state_probe_and_missing_object_probe_degrades(tmp_path, projection):
    class ForbiddenState:
        def observe(self, trace_id):
            pytest.fail("absence must not use StateProbe")

    probe = Probe(facts)
    assert run(tmp_path, probe=probe, projection=projection, state=ForbiddenState()).status == PASSED
    report = run(tmp_path, projection=projection, state=ForbiddenState())
    assert report.status == DEGRADED
    assert "object_absent" in report.degradations()[0][2]
    assert "no ObjectStateProbe" in report.degradations()[0][2]
    assert report.domains[0].steps[0].state_observations == []


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("present", [False, True])
def test_mixed_assertions_share_one_lookup_and_both_are_evaluated(tmp_path, projection, present):
    checks = [absent(), shared.check("name", "actual"), shared.check("code", "C"), absent()]
    objects = [ports.ObservedObject(id=22, fields={"name": "actual", "code": "C"})] if present else []
    probe = Probe(lambda q: facts(q, objects=objects))
    report = run(tmp_path, [api_step(checks=checks)], probe=probe, projection=projection)
    assert report.status == FAILED
    assert len(probe.queries) == 1 and probe.queries[0].fields == ("code", "name")
    actual = [(c.check, c.ok) for c in report.domains[0].steps[0].checks if c.point == "backend_state"]
    assert actual == [("object_absent", not present), ("object_field_equals", present),
                      ("object_field_equals", present), ("object_absent", not present)]
    assert {f.name for f in fields(probe.queries[0])} == shared.QUERY_FIELDS


def test_business_object_and_exact_id_type_and_value_determine_groups(tmp_path):
    probe = Probe(facts)
    checks = [absent(identity=1), absent(identity="1"), absent(identity=1, object_name="document"),
              absent(identity=2), absent(identity=1)]
    assert run(tmp_path, [api_step(checks=checks)], probe=probe).status == PASSED
    assert [(q.object, type(q.id), q.id) for q in probe.queries] == [
        ("record", int, 1), ("record", str, "1"), ("document", int, 1), ("record", int, 2)]


@pytest.mark.parametrize("key,bad", [
    ("observation_id", "stale"), ("projection", "frontend"), ("step_id", "other"),
    ("trace_id", "other"), ("user", "other"), ("session_generation", False),
    ("object", "other"), ("id", "22"), ("fields", ("name",)), ("fields", []),
])
def test_wrong_echo_identity_cannot_prove_absence(tmp_path, key, bad):
    probe = Probe(lambda q: facts(q, query=replace(q, **{key: bad})))
    sr = run(tmp_path, probe=probe).domains[0].steps[0]
    assert sr.status == ERROR and sr.state_observations == []
    assert sr.detail == "Object state returned invalid evidence"


@pytest.mark.parametrize("changes", [
    {"source": ""}, {"source": " "}, {"source": None}, {"complete": 1},
    {"objects": None}, {"objects": ()}, {"objects": [{}]},
    {"objects": [ports.ObservedObject(id=True, fields={})]},
    {"objects": [ports.ObservedObject(id="22", fields={})]},
    {"objects": [ports.ObservedObject(id=22, fields={"unrequested": "sensitive"})]},
])
def test_malformed_or_unrequested_facts_never_become_absence(tmp_path, changes):
    sr = run(tmp_path, probe=Probe(lambda q: facts(q, **changes))).domains[0].steps[0]
    assert sr.status == ERROR and not sr.state_observations
    assert sr.detail == "Object state returned invalid evidence"


@pytest.mark.parametrize("returned", [None, {}, [], False])
def test_no_result_is_distinct_from_valid_empty_lookup(tmp_path, returned):
    sr = run(tmp_path, probe=Probe(lambda q: returned)).domains[0].steps[0]
    assert sr.status == ERROR and not sr.state_observations


def test_incomplete_empty_lookup_is_retained_but_cannot_pass(tmp_path):
    sr = run(tmp_path, probe=Probe(lambda q: facts(q, complete=False))).domains[0].steps[0]
    assert sr.status == ERROR and "incomplete" in sr.detail
    assert len(sr.state_observations) == 1
    assert not any(c.check == "object_absent" for c in sr.checks)


def test_query_failure_is_safe_and_blocks_later_actions(tmp_path):
    secret = "sensitive-query-and-connection-sentinel"
    def fail(query):
        raise RuntimeError(secret)
    api, probe = FakeApi(), Probe(fail)
    report = run(tmp_path, [api_step(), api_step("later")], probe=probe, api=api)
    first, second = report.domains[0].steps
    assert [first.status, second.status] == [ERROR, BLOCKED]
    assert first.detail == "Object state query failed"
    assert len(api.sent) == len(probe.queries) == 1
    assert secret not in repr(report)


def test_stale_or_mutated_queries_are_invalid_even_for_empty_objects(tmp_path):
    probe = Probe(facts)
    assert run(tmp_path, probe=probe).status == PASSED
    old = probe.facts[0]
    probe.callback = lambda q: old
    assert run(tmp_path, probe=probe).domains[0].steps[0].status == ERROR
    assert probe.queries[0].observation_id != probe.queries[1].observation_id
    def mutate(q):
        object.__setattr__(q, "id", 999)
        return facts(q)
    assert run(tmp_path, probe=Probe(mutate)).domains[0].steps[0].status == ERROR


def test_core_owns_empty_snapshot_and_hides_sensitive_identity(tmp_path):
    sentinel = "sensitive-record-identity"
    probe = Probe(facts)
    report = run(tmp_path, [api_step(checks=[absent(identity=sentinel)])], probe=probe)
    sr = report.domains[0].steps[0]
    retained = sr.state_observations[0]
    probe.facts[0].objects.append(ports.ObservedObject(id=sentinel, fields={}))
    object.__setattr__(probe.facts[0].query, "id", "changed")
    assert retained.objects == [] and retained.query.id == sentinel
    assert sentinel not in repr(report) and sentinel not in repr(retained)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_failed_response_still_observes_and_default_continuation_is_preserved(tmp_path, projection):
    first = api_step()
    first["expect"]["response"] = [{"check": "status_equals", "value": 201}]
    probe = Probe(facts)
    report = run(tmp_path, [first, api_step("later")], probe=probe, projection=projection)
    assert [s.status for s in report.domains[0].steps] == [FAILED, PASSED]
    assert len(probe.queries) == 2
    assert report.domains[0].steps[0].checks[-1].check == "object_absent"
    assert report.domains[0].steps[0].checks[-1].ok
    assert report.domains[0].steps[1].after_failures == ["remove"]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_absence_failure_obeys_explicit_stop(tmp_path, projection):
    first = api_step()
    first["on_failure"] = "stop"
    probe = Probe(lambda q: facts(q, count=1))
    report = run(tmp_path, [first, api_step("later")], probe=probe, projection=projection)
    assert [s.status for s in report.domains[0].steps] == [FAILED, BLOCKED]
    assert len(probe.queries) == 1


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("succeed_after,on_timeout,status,calls", [
    (2, "FAIL", PASSED, 1), (100, "FAIL", FAILED, 0), (100, "SKIP", SKIPPED, 0),
])
def test_polling_only_observes_once_after_successful_terminal_response(
        tmp_path, projection, succeed_after, on_timeout, status, calls):
    step = api_step()
    step["poll"] = {"on_timeout": on_timeout}
    probe, clock = Probe(facts), Clock()
    report = run_scenario(write(tmp_path, [step]), adapters(probe, api=SequenceApi(succeed_after)),
        projections=(projection,), poll_config=PollConfig(timeout=2, interval=1),
        now=clock.now, sleep=clock.sleep)
    sr = report.domains[0].steps[0]
    assert sr.status == status and len(probe.queries) == calls
    if calls:
        assert probe.queries[0].trace_id == sr.trace_id
    else:
        assert any("object_absent" in text for text in sr.not_checked)


def ui_step():
    step = shared.ui_step()
    step["expect"]["backend_state"] = [absent()]
    return step


def test_request_associated_live_ui_uses_absence_observer_without_state_probe(tmp_path):
    ui, probe = ScriptedUi(1), Probe(facts)
    report = run(tmp_path, [ui_step()], probe=probe, ui=ui, projection="e2e", users=["owner"])
    assert report.status == PASSED and ui.open_calls == ui.close_calls == 1
    sr = report.domains[0].steps[0]
    query = probe.queries[0]
    assert query.fields == () and query.projection == "e2e"
    assert query.user == "owner" and query.session_generation == 1 and query.trace_id == sr.trace_id
    assert len(sr.state_observations) == len(report.domains[0].provider_recordings) == 1


def test_frontend_mock_does_not_query_storage(tmp_path):
    ui = ScriptedUi(1)
    probe = Probe(lambda q: pytest.fail("frontend must not query storage"))
    report = run_scenario(write(tmp_path, [ui_step()]), adapters(probe, ui=ui),
                          projections=("frontend",), mock_plan=ui.plan())
    assert report.status == PASSED and probe.queries == []
    sr = report.domains[0].steps[0]
    assert sr.state_observations == [] and any("backend_state" in text for text in sr.not_checked)


@pytest.mark.parametrize("response", [True, False])
def test_contract_keeps_absence_outside_compatibility_evidence(tmp_path, response):
    probe = Probe(facts)
    report = run_scenario(write(tmp_path, [api_step(response=response)]), adapters(probe),
                          projections=("backend", "contract"))
    assert len(probe.queries) == 1
    domain = report.domains[1]
    assert domain.status == (PASSED if response else EMPTY)
    assert domain.not_checked == ["remove: object_absent is outside contract scope"]
    assert not any(c.check == "object_absent" for c in domain.checks)


def test_contract_error_path_reports_both_object_check_kinds(tmp_path):
    scenario = load_scenario(write(tmp_path, [api_step(checks=[absent(), shared.check(), absent()])]))
    domain = contract.run(scenario, [], FakeNormalizer(), execution_steps=[])
    assert domain.steps[0].status == ERROR
    assert domain.not_checked == ["remove: object_absent is outside contract scope",
                                  "remove: object_field_equals is outside contract scope"]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("payload", [{}, {"id": None}, {"id": True}, {"id": False}, {"id": ""},
                                     {"id": 1.5}, {"id": []}, {"id": {}}])
def test_missing_or_invalid_prior_identity_blocks_before_consuming_action(tmp_path, projection, payload):
    source = api_step("source", checks=[])
    consumer = api_step(checks=[absent(identity={"from_step": "source", "response_field": "id"})])
    api = FakeApi({("GET", "records"): {"json": {"success": True, "data": payload}}})
    probe = Probe(facts)
    report = run(tmp_path, [source, consumer], probe=probe, api=api, projection=projection)
    assert [s.status for s in report.domains[0].steps] == [PASSED, BLOCKED]
    assert len(api.sent) == 1 and probe.queries == []
    assert report.domains[0].steps[1].blocked_by == ["source"]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_users_and_replaced_sessions_keep_exact_query_identity(tmp_path, projection):
    steps = [api_step(name) for name in ("first", "again", "renewed", "peer", "public")]
    for step in steps[:3]:
        step["user"] = "owner"
    steps[2]["session"] = "new"
    steps[3]["user"], steps[4]["user"] = "peer", "anonymous"
    probe = Probe(facts)
    assert run(tmp_path, steps, probe=probe, projection=projection, users=["owner", "peer", "anonymous"]).status == PASSED
    assert [(q.user, q.session_generation) for q in probe.queries] == [
        ("owner", 1), ("owner", 1), ("owner", 2), ("peer", 1), (None, 0)]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("identity", [44, "44"])
def test_included_absence_receives_supplied_identity_and_mapped_user(tmp_path, projection, identity):
    child = document(request(assertions=[absent(identity={"from_parameter": "record_id"})]))
    child["scenario"] = "shared.absence"
    root = document({"id": "remove", "do": {"include": "shared.absence"},
        "with": {"record_id": {"from_parameter": "parent_id"}}, "with_users": {"reader": "owner"}},
        parameters={"parent_id": identity})
    root["users"] = ["owner"]
    path, _ = write_bundle(tmp_path, root, child)
    probe = Probe(facts)
    report = run_scenario(path, adapters(probe), projections=(projection,))
    assert report.status == PASSED
    query = probe.queries[0]
    assert type(query.id) is type(identity) and query.id == identity
    assert query.user == "owner" and query.step_id == "remove/read"


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("present", [False, True])
def test_named_include_result_preserves_identity_and_failure_behavior(tmp_path, projection, present):
    child = document(api_step("create", checks=[]))
    child["scenario"] = "shared.create"
    child["results"] = {"record_id": {"from_step": "create", "response_field": "id"}}
    consume = api_step(checks=[absent(identity={"from_step": "setup", "result": "record_id"})])
    consume["on_failure"] = "stop"
    root = document({"id": "setup", "do": {"include": "shared.create"}}, consume, api_step("later", checks=[]))
    path, _ = write_bundle(tmp_path, root, child)
    api = FakeApi({("GET", "records"): {"json": {"success": True, "data": {"id": "record-44"}}}})
    probe = Probe(lambda q: facts(q, count=int(present)))
    report = run_scenario(path, adapters(probe, api=api), projections=(projection,))
    assert [s.status for s in report.domains[0].steps] == ([PASSED, FAILED, BLOCKED] if present else [PASSED] * 3)
    assert len(probe.queries) == 1 and probe.queries[0].id == "record-44"
    assert report.domains[0].steps[1].binding_sources


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("identity,present", [(44, False), ("44", False), (44, True), (True, False)])
def test_sequential_flow_consumer_preserves_selector_and_blocks_invalid_ids(tmp_path, projection, identity, present):
    source = flow_scenario("records.create", [api_step("create", checks=[])],
        writes={"record_id": {"from_step": "create", "response_field": "id"}})
    consumer = flow_scenario("records.remove", [api_step(checks=[absent(identity={"from_flow": "record_id"})])])
    path = flow_path(tmp_path, [source, consumer], parameters={"record_id": {}})
    api = FakeApi({("GET", "records"): {"json": {"success": True, "data": {"id": identity}}}})
    probe = Probe(lambda q: facts(q, count=int(present)))
    report = run_flow(path, adapters(probe, api=api), projections=(projection,))
    first, second = [item.domains[0] for item in report.scenarios]
    assert first.status == PASSED
    assert second.steps[0].status == (BLOCKED if type(identity) is bool else FAILED if present else PASSED)
    assert second.status == (DEGRADED if type(identity) is bool else FAILED if present else PASSED)
    if type(identity) is bool:
        assert len(api.sent) == 1 and probe.queries == []
        assert second.steps[0].blocked_by == ["flow:record_id"]
    else:
        query = probe.queries[0]
        assert len(api.sent) == 2 and len(probe.queries) == 1
        assert type(query.id) is type(identity) and query.id == identity
        assert query.step_id == "n1/remove" and query.user == "owner" and query.session_generation == 1
        assert first.flow_writes["record_id"].version == second.flow_reads["record_id"].version == 1
