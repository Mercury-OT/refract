"""Live object observation uses selectors, fresh identity and core-owned facts."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import inspect
import json

import pytest
import yaml

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.projection import contract
from refracto.report import BLOCKED, DEGRADED, EMPTY, ERROR, FAILED, PASSED, SKIPPED, StepResult
from refracto.runner import Adapters, PollConfig, run_scenario
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeStateProbe
from tests.ui_support import ScriptedUi


QUERY_FIELDS = {"observation_id", "projection", "step_id", "trace_id", "user",
                "session_generation", "object", "id", "fields"}


def check(field="name", value="actual-name", *, identity=22, object_name="record"):
    return {"check": "object_field_equals", "object": object_name, "id": identity,
            "field": field, "value": value}


def api_step(identity="read", *, checks=None, response=True):
    expect = {"backend_state": [check()] if checks is None else checks}
    if response:
        expect["response"] = [{"check": "success"}]
    return {"id": identity, "do": {"request": {"method": "GET", "path": ["records"]}},
            "expect": expect}


def write(tmp_path, steps, *, users=None, parameters=None, scenario_id="records.object_state"):
    steps, parameters = deepcopy(steps), deepcopy(parameters or {})
    # Approved object IDs are references. Lift the test fixture's concrete IDs
    # into parameters so the real loader and pre-action binder both execute.
    for step in steps:
        for assertion in step.get("expect", {}).get("backend_state", []):
            if assertion["check"] == "object_field_equals" and type(assertion["id"]) is not dict:
                name = f"object_id_{len(parameters)}"
                parameters[name] = assertion["id"]
                assertion["id"] = {"from_parameter": name}
    path = tmp_path / "object-state.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "scenario": scenario_id,
        "users": users or [], "parameters": parameters, "steps": steps}, sort_keys=False),
        encoding="utf-8")
    return path


def resolve(action):
    return ports.RequestSpec(action.method, action.path, deepcopy(action.body))


class Probe(ports.ObjectStateProbe):
    def __init__(self, callback=None):
        self.queries = []
        self.facts = []
        self.callback = callback

    def observe_object(self, query):
        self.queries.append(query)
        facts = (self.callback(query) if self.callback else ports.ObjectStateFacts(
            query=query, source="memory-records", complete=True,
            objects=[ports.ObservedObject(id=query.id, fields={"name": "actual-name"})]))
        self.facts.append(facts)
        return facts


def adapters(probe=None, *, api=None, ui=None, state=None, normalizer=None):
    return Adapters(FakeAuth(), api or FakeApi(), state, ui, FakeRecorder, resolve,
                    normalizer or FakeNormalizer(), object_state=probe)


def run(tmp_path, steps=None, *, probe=None, projection="backend", users=None,
        parameters=None, **kwargs):
    path = write(tmp_path, [api_step()] if steps is None else steps,
                 users=users, parameters=parameters)
    return run_scenario(path, adapters(probe, **kwargs), projections=(projection,))


def facts(selector, value="actual-name", **changes):
    return replace(ports.ObjectStateFacts(query=selector, source="memory-records", complete=True,
        objects=[ports.ObservedObject(id=selector.id, fields={"name": value})]), **changes)


def test_exact_object_observation_port_and_sensitive_shapes():
    assert set(inspect.signature(ports.ObjectStateProbe.observe_object).parameters) == {"self", "query"}
    assert {f.name for f in fields(ports.ObjectStateQuery)} == QUERY_FIELDS
    assert {f.name for f in fields(ports.ObservedObject)} == {"id", "fields"}
    assert {f.name for f in fields(ports.ObjectStateFacts)} == {"query", "source", "complete", "objects"}
    assert all(f.kw_only for f in fields(ports.ObjectStateQuery))
    assert inspect.signature(Adapters).parameters["object_state"].kind is inspect.Parameter.KEYWORD_ONLY
    query = ports.ObjectStateQuery(observation_id="fresh", projection="backend", step_id="read",
        trace_id="trace", user=None, session_generation=0, object="record", id=22,
        fields=("name",))
    assert not hasattr(query, "__dict__")
    with pytest.raises(FrozenInstanceError):
        query.id = 23
    with pytest.raises(TypeError):
        query.fields[0] = "other"
    sr_fields = {f.name: f for f in fields(StepResult)}
    assert sr_fields["state_observations"].kw_only
    assert sr_fields["state_observations"].metadata["sensitive"]
    assert not sr_fields["state_observations"].repr


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_grouped_one_shot_query_contains_no_expectations_or_binding_environment(tmp_path, projection):
    secret = "expected-only-secret"
    checks = [check("z", {"from_parameter": "wanted"}), check("name"),
              check("z", {"from_parameter": "wanted"}), check("value", 0), check("expect", False)]
    probe = Probe(lambda q: ports.ObjectStateFacts(query=q, source="memory-records", complete=True,
        objects=[ports.ObservedObject(id=q.id,
            fields={"name": "actual-name", "z": "other", "value": 0, "expect": False})]))
    report = run(tmp_path, [api_step(checks=checks)], probe=probe, projection=projection,
                 users=["owner"], parameters={"wanted": secret, "unused": "unused-secret"})
    assert report.status == FAILED
    assert len(probe.queries) == 1
    query = probe.queries[0]
    assert query.fields == ("expect", "name", "value", "z")
    assert query.object == "record" and type(query.id) is int and query.id == 22
    assert query.projection == projection and query.user == "owner" and query.session_generation == 1
    sr = report.domains[0].steps[0]
    assert query.step_id == sr.step_id == "read" and query.trace_id == sr.trace_id
    assert type(query.observation_id) is str and query.observation_id
    visible = json.dumps({f.name: getattr(query, f.name) for f in fields(query)})
    assert secret not in visible and "unused-secret" not in visible
    assert all(type(getattr(query, f.name)) in (str, int, tuple) or getattr(query, f.name) is None
               for f in fields(query))
    assert len([c for c in sr.checks if c.check == "object_field_equals"]) == 5
    assert not report.degradations()  # no legacy StateProbe is needed for object-only checks


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_only_object_assertions_can_pass_without_trace_probe(tmp_path, projection):
    probe = Probe()
    report = run(tmp_path, [api_step(response=False)], probe=probe, projection=projection)
    assert report.status == PASSED
    assert len(probe.queries) == 1
    assert probe.queries[0].user is None and probe.queries[0].session_generation == 0
    assert report.degradations() == []


@pytest.mark.parametrize("expected,observed,passed", [
    (None, None, True), (0, 0, True), (False, False, True), ("", "", True),
    (True, 1, False), (False, 0, False), (0, False, False), (1, True, False),
    (None, "", False), ("", None, False), (1, 1.0, False),
    ("actual-name", {"nested": [0, False, None]}, False),
    ("actual-name", ["actual-name"], False),
])
def test_scalar_comparison_is_strict_and_present_falsy_values_are_real(tmp_path, expected, observed, passed):
    probe = Probe(lambda q: facts(q, observed))
    report = run(tmp_path, [api_step(checks=[check(value=expected)])], probe=probe)
    assert report.domains[0].steps[0].status == (PASSED if passed else FAILED)
    assert report.status == (PASSED if passed else FAILED)


@pytest.mark.parametrize("objects", [[], [ports.ObservedObject(id=22, fields={})]])
def test_complete_empty_or_missing_field_fails_instead_of_becoming_null(tmp_path, objects):
    report = run(tmp_path, [api_step(checks=[check(value=None)])],
                 probe=Probe(lambda q: facts(q, objects=objects)))
    sr = report.domains[0].steps[0]
    assert sr.status == FAILED and len(sr.state_observations) == 1
    assert any(c.check == "object_field_equals" and not c.ok for c in sr.checks)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_missing_probe_is_visible_degradation(tmp_path, projection):
    report = run(tmp_path, projection=projection)
    assert report.status == DEGRADED
    assert "no ObjectStateProbe" in report.degradations()[0][2]
    assert report.domains[0].steps[0].state_observations == []


def test_no_declared_observation_never_queries(tmp_path):
    probe = Probe(lambda q: pytest.fail("unexpected storage query"))
    report = run(tmp_path, [api_step(checks=[])], probe=probe)
    assert report.status == PASSED and probe.queries == []


@pytest.mark.parametrize("key,bad", [
    ("observation_id", "stale"), ("projection", "frontend"), ("step_id", "other"),
    ("trace_id", "other"), ("user", "other"), ("session_generation", False),
    ("object", "other"), ("id", "22"), ("fields", ("other",)), ("fields", ["name"]),
])
def test_all_query_echo_identity_mismatches_are_rejected(tmp_path, key, bad):
    probe = Probe(lambda q: facts(q, query=replace(q, **{key: bad})))
    sr = run(tmp_path, probe=probe).domains[0].steps[0]
    assert sr.status == ERROR and sr.state_observations == []
    assert sr.detail == "Object state returned invalid evidence"


@pytest.mark.parametrize("changed", [
    {"source": ""}, {"source": 1}, {"complete": 1}, {"objects": ()},
    {"objects": [dict(id=22, fields={"name": "actual-name"})]},
    {"objects": [ports.ObservedObject(id=True, fields={"name": "actual-name"})]},
    {"objects": [ports.ObservedObject(id="22", fields={"name": "actual-name"})]},
    {"objects": [ports.ObservedObject(id=22, fields=[]) ]},
    {"objects": [ports.ObservedObject(id=22, fields={1: "actual-name"})]},
    {"objects": [ports.ObservedObject(id=22, fields={"unrequested": "actual-name"})]},
    {"objects": [ports.ObservedObject(id=22, fields={"name": float("nan")})]},
    {"objects": [ports.ObservedObject(id=22, fields={"name": {"nested": float("inf")}})]},
    {"objects": [ports.ObservedObject(id=22, fields={"name": object()})]},
])
def test_malformed_facts_are_errors_and_never_retained(tmp_path, changed):
    sr = run(tmp_path, probe=Probe(lambda q: facts(q, **changed))).domains[0].steps[0]
    assert sr.status == ERROR and sr.state_observations == []
    assert sr.detail == "Object state returned invalid evidence"


def test_cyclic_observed_data_is_error(tmp_path):
    cycle = []
    cycle.append(cycle)
    sr = run(tmp_path, probe=Probe(lambda q: facts(q, cycle))).domains[0].steps[0]
    assert sr.status == ERROR and not sr.state_observations


@pytest.mark.parametrize("changed,detail", [
    ({"complete": False}, "incomplete"),
    ({"objects": [ports.ObservedObject(id=22, fields={"name": "actual-name"})] * 2}, "ambiguous"),
])
def test_well_formed_incomplete_or_ambiguous_observation_errors_without_claiming_pass(tmp_path, changed, detail):
    sr = run(tmp_path, probe=Probe(lambda q: facts(q, **changed))).domains[0].steps[0]
    assert sr.status == ERROR and detail in sr.detail
    assert len(sr.state_observations) == 1
    assert not any(c.check == "object_field_equals" for c in sr.checks)


def test_probe_exception_is_value_free_error_and_blocks_later_steps(tmp_path):
    sentinel = "SELECT secret FROM /private/example.db WHERE id=987654"

    def fail(query):
        raise RuntimeError(sentinel)

    report = run(tmp_path, [api_step(), api_step("later")], probe=Probe(fail))
    first, second = report.domains[0].steps
    assert first.status == ERROR and second.status == BLOCKED
    assert first.detail == "Object state query failed"
    assert sentinel not in repr(report) and sentinel not in first.detail
    assert first.checks[0].ok  # the successful real response is not erased


def test_observation_evidence_is_owned_and_hidden_from_default_report_repr(tmp_path):
    sentinel = "observed-only-secret"
    probe = Probe(lambda q: facts(q, {"nested": [sentinel]}))
    report = run(tmp_path, probe=probe)
    sr = report.domains[0].steps[0]
    assert sr.status == FAILED
    retained = sr.state_observations[0]
    probe.facts[0].objects[0].fields["name"]["nested"][0] = "changed"
    probe.facts[0].objects.clear()
    assert retained.objects[0].fields["name"] == {"nested": [sentinel]}
    assert sentinel not in repr(report)
    assert sentinel not in repr(retained) and sentinel not in repr(retained.objects[0])


def test_protected_query_cannot_be_rewritten_by_probe(tmp_path):
    def mutate(query):
        object.__setattr__(query, "id", 23)
        return facts(query)
    sr = run(tmp_path, probe=Probe(mutate)).domains[0].steps[0]
    assert sr.status == ERROR and not sr.state_observations


def test_query_nonce_rejects_cross_run_stale_facts(tmp_path):
    probe = Probe()
    assert run(tmp_path, probe=probe).status == PASSED
    old = probe.facts[0]
    probe.callback = lambda q: old
    sr = run(tmp_path, probe=probe).domains[0].steps[0]
    assert probe.queries[0].observation_id != probe.queries[1].observation_id
    assert sr.status == ERROR and not sr.state_observations


def test_int_and_string_ids_are_distinct_groups_and_second_error_keeps_first_facts(tmp_path):
    def observe(query):
        if type(query.id) is str:
            raise RuntimeError("later query failed")
        return facts(query)
    probe = Probe(observe)
    sr = run(tmp_path, [api_step(checks=[check(identity=1), check(identity="1")])],
             probe=probe).domains[0].steps[0]
    assert [(type(q.id), q.id) for q in probe.queries] == [(int, 1), (str, "1")]
    assert sr.status == ERROR and len(sr.state_observations) == 1
    assert sr.state_observations[0].query.id == 1
    assert sr.checks[0].ok


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_failed_response_still_observes_and_default_continuation_is_unchanged(tmp_path, projection):
    first = api_step()
    first["expect"]["response"] = [{"check": "status_equals", "value": 201}]
    probe = Probe()
    report = run(tmp_path, [first, api_step("later")], probe=probe, projection=projection)
    assert [s.status for s in report.domains[0].steps] == [FAILED, PASSED]
    assert len(probe.queries) == 2
    assert report.domains[0].steps[1].after_failures == ["read"]


class Clock:
    def __init__(self):
        self.time = 0

    def now(self):
        return self.time

    def sleep(self, duration):
        self.time += duration


class SequenceApi(FakeApi):
    def __init__(self, succeed_after):
        super().__init__()
        self.succeed_after = succeed_after

    def send(self, spec, session):
        response = super().send(spec, session)
        response.json = {"success": len(self.sent) >= self.succeed_after}
        return response


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("succeed_after,on_timeout,expected,calls", [
    (2, "FAIL", PASSED, 1), (100, "FAIL", FAILED, 0), (100, "SKIP", SKIPPED, 0),
])
def test_object_query_runs_once_only_after_successful_poll_terminal_response(
        tmp_path, projection, succeed_after, on_timeout, expected, calls):
    step = api_step()
    step["poll"] = {"on_timeout": on_timeout}
    probe, api, clock = Probe(), SequenceApi(succeed_after), Clock()
    report = run_scenario(write(tmp_path, [step]), adapters(probe, api=api),
        projections=(projection,), poll_config=PollConfig(timeout=2, interval=1),
        now=clock.now, sleep=clock.sleep)
    sr = report.domains[0].steps[0]
    assert sr.status == expected and len(probe.queries) == calls
    assert len(api.sent) > 1
    if calls:
        assert probe.queries[0].trace_id == sr.trace_id
    else:
        assert any("object_field_equals" in text for text in sr.not_checked)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_span_probe_and_object_probe_remain_separate(tmp_path, projection):
    class State(FakeStateProbe):
        def __init__(self):
            self.traces = []

        def observe(self, trace_id):
            self.traces.append(trace_id)
            return ports.StateFacts(trace_id, [ports.Span("saved", {})])

    state, probe = State(), Probe()
    report = run(tmp_path, [api_step(checks=[check(), {"check": "span_exists", "span": "saved"}])],
                 probe=probe, state=state, projection=projection)
    assert report.status == PASSED
    assert state.traces == [probe.queries[0].trace_id]
    assert {c.check for c in report.domains[0].checks} == {"success", "span_exists", "object_field_equals"}


def ui_step():
    return {"id": "save", "do": "click", "target": "records.save", "expect": {
        "request": {"method": "POST", "path": ["items"], "body": {"name": "alpha"}},
        "ui": [{"check": "visible", "anchor": "rows"}],
        "response": [{"check": "success"}], "backend_state": [check()]}}


def test_live_ui_uses_the_shared_observer_after_real_response(tmp_path):
    ui, probe = ScriptedUi(1), Probe()
    report = run(tmp_path, [ui_step()], probe=probe, ui=ui, projection="e2e", users=["owner"])
    assert report.status == PASSED and ui.open_calls == ui.close_calls == 1
    query = probe.queries[0]
    assert query.projection == "e2e" and query.user == "owner" and query.session_generation == 1
    assert query.trace_id == report.domains[0].steps[0].trace_id
    assert len(report.domains[0].provider_recordings) == 1


def test_frontend_mock_never_queries_storage_and_marks_out_of_scope(tmp_path):
    ui = ScriptedUi(1)
    probe = Probe(lambda q: pytest.fail("frontend must not query storage"))
    report = run_scenario(write(tmp_path, [ui_step()]), adapters(probe, ui=ui),
                          projections=("frontend",), mock_plan=ui.plan())
    assert report.status == PASSED and probe.queries == []
    sr = report.domains[0].steps[0]
    assert sr.state_observations == [] and any("backend_state" in text for text in sr.not_checked)


@pytest.mark.parametrize("response", [True, False])
def test_contract_records_object_checks_out_of_scope_even_for_empty_contract(tmp_path, response):
    probe = Probe()
    report = run_scenario(write(tmp_path, [api_step(response=response)]), adapters(probe),
                          projections=("backend", "contract"))
    assert len(probe.queries) == 1  # backend only
    domain = report.domains[1]
    assert domain.status == (PASSED if response else EMPTY)
    assert domain.not_checked == ["read: object_field_equals is outside contract scope"]
    assert not any(c.check == "object_field_equals" for c in domain.checks)


def test_contract_error_path_still_reports_object_checks_not_checked(tmp_path):
    scenario = load_scenario(write(tmp_path, [api_step()]))
    domain = contract.run(scenario, [], FakeNormalizer(), execution_steps=[])
    assert domain.steps[0].status == ERROR
    assert domain.not_checked == ["read: object_field_equals is outside contract scope"]


def test_normalizer_is_not_reused_for_object_facts(tmp_path):
    class CountingNormalizer(FakeNormalizer):
        def __init__(self):
            self.calls = 0

        def normalize(self, response):
            self.calls += 1
            return super().normalize(response)

    normalizer, probe = CountingNormalizer(), Probe()
    assert run(tmp_path, probe=probe, normalizer=normalizer).status == PASSED
    assert normalizer.calls == len(probe.queries) == 1


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_query_reports_effective_users_and_explicit_session_generations(tmp_path, projection):
    steps = [api_step(name) for name in ("first", "again", "renewed", "peer", "public")]
    for step in steps[:3]:
        step["user"] = "owner"
    steps[2]["session"] = "new"
    steps[3]["user"], steps[4]["user"] = "peer", "anonymous"
    probe = Probe()
    report = run(tmp_path, steps, probe=probe, projection=projection,
                 users=["owner", "peer", "anonymous"])
    assert report.status == PASSED
    assert [(q.user, q.session_generation) for q in probe.queries] == [
        ("owner", 1), ("owner", 1), ("owner", 2), ("peer", 1), (None, 0)]
    assert len({q.observation_id for q in probe.queries}) == 5


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("invalid_id", [None, True, False, [], {}, 1.5, ""])
def test_invalid_prior_id_blocks_before_action_or_probe(tmp_path, projection, invalid_id):
    source = api_step("create", checks=[])
    consumer = api_step(checks=[check(identity={"from_step": "create", "response_field": "id"})])
    api = FakeApi({("GET", "records"): {"json": {"success": True, "data": {"id": invalid_id}}}})
    probe = Probe()
    report = run(tmp_path, [source, consumer], probe=probe, api=api, projection=projection)
    assert [s.status for s in report.domains[0].steps] == [PASSED, BLOCKED]
    assert len(api.sent) == 1 and probe.queries == []
    assert report.domains[0].steps[1].blocked_by == ["create"]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_id_and_expected_prior_response_references_are_resolved_before_observation(tmp_path, projection):
    source = api_step("create", checks=[])
    consumer = api_step(checks=[check(
        value={"from_step": "create", "response_field": "name"},
        identity={"from_step": "create", "response_field": "id"})])
    api = FakeApi({("GET", "records"): {"json": {
        "success": True, "data": {"id": 22, "name": "actual-name"}}}})
    probe = Probe()
    report = run(tmp_path, [source, consumer], probe=probe, api=api, projection=projection)
    assert report.status == PASSED
    assert len(probe.queries) == 1 and probe.queries[0].id == 22
    assert report.domains[0].steps[1].binding_sources


def test_object_failure_keeps_explicit_on_failure_stop(tmp_path):
    first = api_step()
    first["on_failure"] = "stop"
    probe = Probe(lambda q: facts(q, "wrong-name"))
    report = run(tmp_path, [first, api_step("later")], probe=probe)
    assert [s.status for s in report.domains[0].steps] == [FAILED, BLOCKED]
    assert len(probe.queries) == 1


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_included_observation_receives_parent_id_and_mapped_user(tmp_path, projection):
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    child_path = write(child_dir, [api_step(checks=[check(identity={"from_parameter": "record_id"})])],
        parameters={"record_id": 22}, users=["worker"], scenario_id="records.child")
    parent_path = write(tmp_path, [{"id": "setup", "do": {"include": "records.child"},
        "with": {"record_id": {"from_parameter": "parent_id"}},
        "with_users": {"worker": "owner"}}], parameters={"parent_id": 44}, users=["owner"])
    parent_path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"records.child": {"path": "child/object-state.yaml",
            "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    probe = Probe()
    report = run_scenario(parent_path, adapters(probe), projections=(projection,))
    assert report.status == PASSED
    query = probe.queries[0]
    assert query.id == 44 and query.user == "owner" and query.step_id == "setup/read"
    assert report.domains[0].steps[0].state_observations[0].query == query
