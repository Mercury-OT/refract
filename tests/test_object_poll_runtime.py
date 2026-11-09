"""Only complete object mismatches retry; requests, failures and evidence stay honest."""
from copy import deepcopy
from dataclasses import fields, replace

import pytest

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import PollPolicy
from refracto.projection import backend, e2e
from refracto.report import BLOCKED, DEGRADED, ERROR, FAILED, PASSED, ObjectPollResult
from refracto.runner import PollConfig, run_flow, run_scenario
from tests.fakes import FakeApi, FakeNormalizer, FakeRecorder
from tests.test_flow_runtime import flow_path, scenario as flow_scenario, request as flow_request
from tests.test_object_absence_runtime import absent, facts, write
from tests.test_object_state_runtime import Probe, adapters, Clock, api_step, check, ui_step
from tests.test_scenario_include import write_bundle
from tests.test_object_state_declaration import document
from tests.ui_support import ScriptedUi


def waiting(*, checks=None, **changes):
    raw = api_step("remove", checks=[absent()] if checks is None else checks)
    raw["do"]["request"]["method"] = "DELETE"
    raw["object_poll"] = {"on_timeout": "FAIL"}
    raw.update(changes)
    return raw


class RecordingClock(Clock):
    def __init__(self):
        super().__init__()
        self.sleeps = []

    def sleep(self, duration):
        self.sleeps.append(duration)
        super().sleep(duration)


def execute(tmp_path, probe, *, steps=None, projection="backend", clock=None,
            timeout=2, interval=0.5, **options):
    clock = clock or RecordingClock()
    ad = adapters(probe, **options)
    path = write(tmp_path, [waiting()] if steps is None else steps)
    result = run_scenario(path, ad, projections=(projection,),
        poll_config=PollConfig(timeout=timeout, interval=interval), now=clock.now, sleep=clock.sleep)
    return result, ad, clock


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("count", [1, 3])
def test_success_repeats_only_fresh_read_not_action_or_recording(tmp_path, projection, count):
    probe = Probe(lambda q: facts(q, count=int(len(probe.queries) < count)))
    report, ad, clock = execute(tmp_path, probe, projection=projection)
    sr = report.domains[0].steps[0]
    assert report.status == sr.status == PASSED
    assert len(ad.api.sent) == sr.attempts == len(report.domains[0].provider_recordings) == 1
    assert len(probe.queries) == len(sr.state_observations) == count
    assert len({q.observation_id for q in probe.queries}) == count
    assert len({(q.trace_id, q.step_id, q.user, q.session_generation, q.object, q.id, q.fields)
                for q in probe.queries}) == 1
    assert sr.object_poll == ObjectPollResult(2, 0.5, count, (count - 1) * 0.5, "matched")
    record = report.domains[0].provider_recordings[0]
    assert record.attempt_index == 0 and record.is_final
    assert len(sr.checks) == 2 and all(c.ok for c in sr.checks)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_timeout_clamps_sleep_and_starts_no_read_at_deadline(tmp_path, projection):
    probe = Probe(lambda q: facts(q, count=1))
    report, ad, clock = execute(tmp_path, probe, projection=projection, timeout=2.5, interval=1)
    sr = report.domains[0].steps[0]
    assert sr.status == report.status == FAILED
    assert len(ad.api.sent) == 1 and len(probe.queries) == 3
    assert clock.sleeps == [1, 1, 0.5]
    assert sr.object_poll == ObjectPollResult(2.5, 1, 3, 2.5, "timeout")
    assert sr.detail == "Object state observation deadline expired"
    assert len([c for c in sr.checks if c.check == "object_absent"]) == 1


@pytest.mark.parametrize("elapsed", [2, 3])
def test_matching_read_at_or_after_deadline_is_retained_but_cannot_pass(tmp_path, elapsed):
    clock = RecordingClock()
    def late(query):
        clock.time += elapsed
        return facts(query)
    report, ad, _ = execute(tmp_path, Probe(late), clock=clock)
    sr = report.domains[0].steps[0]
    assert report.status == sr.status == FAILED
    assert all(c.ok for c in sr.checks)  # snapshot truth does not erase deadline failure
    assert len(sr.state_observations) == 1 and len(ad.api.sent) == 1
    assert sr.object_poll == ObjectPollResult(2, 0.5, 1, elapsed, "timeout")
    assert not clock.sleeps and "deadline" in sr.detail


def test_budget_starts_after_response_and_before_initial_query(tmp_path):
    clock = RecordingClock()
    class SlowApi(FakeApi):
        def send(self, spec, credentials):
            clock.time += 10
            return super().send(spec, credentials)
    report, _, _ = execute(tmp_path, Probe(facts), api=SlowApi(), clock=clock)
    assert report.status == PASSED and report.domains[0].steps[0].object_poll.elapsed == 0
    assert clock.time == 10


def test_already_expired_initial_window_makes_no_probe_call(tmp_path):
    class JumpClock(RecordingClock):
        def now(self):
            value = self.time
            self.time = 2
            return value
    probe = Probe(facts)
    report, ad, _ = execute(tmp_path, probe, clock=JumpClock())
    sr = report.domains[0].steps[0]
    assert sr.status == FAILED and sr.object_poll.outcome == "timeout"
    assert sr.object_poll.attempts == 0 and not probe.queries and not sr.state_observations
    assert len(ad.api.sent) == 1


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("eventually_same", [False, True])
def test_all_conditions_require_one_fresh_snapshot_not_accumulated_matches(tmp_path, projection, eventually_same):
    def observe(q):
        attempt = len(probe.queries)
        values = {"name": "A", "code": "wrong"} if attempt % 2 else {"name": "wrong", "code": "B"}
        if eventually_same and attempt == 3:
            values = {"name": "A", "code": "B"}
        return facts(q, objects=[ports.ObservedObject(q.id, values)])
    probe = Probe(observe)
    report, _, _ = execute(tmp_path, probe, projection=projection,
        steps=[waiting(checks=[check("name", "A"), check("code", "B")])])
    sr = report.domains[0].steps[0]
    assert sr.status == (PASSED if eventually_same else FAILED)
    assert len(sr.checks) == 3
    assert len(probe.queries) == (3 if eventually_same else 4)
    assert all(q.fields == ("code", "name") for q in probe.queries)


def test_absence_and_field_equality_cannot_accumulate_across_snapshots(tmp_path):
    def observe(q):
        return facts(q, objects=[] if len(probe.queries) % 2 else
                     [ports.ObservedObject(q.id, {"name": "A"})])
    probe = Probe(observe)
    report, _, _ = execute(tmp_path, probe, steps=[waiting(checks=[absent(), check("name", "A")])])
    assert report.status == FAILED and report.domains[0].steps[0].object_poll.outcome == "timeout"


@pytest.mark.parametrize("kind", ["raise", "malformed", "incomplete", "ambiguous", "wrong_id", "stale"])
@pytest.mark.parametrize("late", [False, True])
def test_evidence_errors_stop_immediately_even_if_late_and_never_retry(tmp_path, kind, late):
    clock = RecordingClock()
    def invalid(q):
        if late:
            clock.time += 3
        if kind == "raise":
            raise RuntimeError("secret-query-sentinel")
        if kind == "malformed":
            return None
        if kind == "incomplete":
            return facts(q, complete=False)
        if kind == "ambiguous":
            return facts(q, count=2)
        if kind == "wrong_id":
            return facts(q, objects=[ports.ObservedObject("22", {})])
        return facts(q, query=replace(q, observation_id="stale"))
    probe = Probe(invalid)
    report, ad, _ = execute(tmp_path, probe, clock=clock, steps=[waiting(), api_step("later")])
    first, later = report.domains[0].steps
    assert [first.status, later.status] == [ERROR, BLOCKED]
    assert first.object_poll == ObjectPollResult(2, 0.5, 1, 3 if late else 0, "error")
    assert len(ad.api.sent) == len(probe.queries) == 1 and not clock.sleeps
    assert len(first.state_observations) == int(kind in {"incomplete", "ambiguous"})
    assert "secret-query-sentinel" not in repr(report) and "secret-query-sentinel" not in first.detail


def test_midstream_error_keeps_earlier_snapshot_and_counts_failed_read(tmp_path):
    def observe(q):
        if len(probe.queries) == 1:
            return facts(q, count=1)
        raise ValueError("secret")
    probe = Probe(observe)
    report, _, _ = execute(tmp_path, probe)
    sr = report.domains[0].steps[0]
    assert sr.status == ERROR and sr.object_poll.attempts == 2
    assert sr.object_poll.elapsed == 0.5 and len(sr.state_observations) == 1
    assert all(c.point != "backend_state" for c in sr.checks)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_missing_probe_is_visible_degradation_with_no_attempts(tmp_path, projection):
    report, _, _ = execute(tmp_path, None, projection=projection)
    sr = report.domains[0].steps[0]
    assert report.status == DEGRADED and not report.passed
    assert sr.object_poll == ObjectPollResult(2, 0.5, 0, 0, "unavailable")
    assert sr.skipped and not sr.state_observations


@pytest.mark.parametrize("on_failure", [None, "stop"])
def test_timeout_uses_existing_continue_or_stop_policy(tmp_path, on_failure):
    raw = waiting()
    if on_failure:
        raw["on_failure"] = on_failure
    later = api_step("later", checks=[])
    report, ad, _ = execute(tmp_path, Probe(lambda q: facts(q, count=1)), steps=[raw, later])
    first, second = report.domains[0].steps
    assert first.status == FAILED
    assert second.status == (BLOCKED if on_failure else PASSED)
    assert len(ad.api.sent) == (1 if on_failure else 2)
    if not on_failure:
        assert second.after_failures == ["remove"]


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_eventual_object_match_cannot_erase_failed_response(tmp_path, projection):
    api = FakeApi({("DELETE", "records"): {"status": 500, "json": {"success": False}}})
    report, _, _ = execute(tmp_path, Probe(facts), api=api, projection=projection)
    sr = report.domains[0].steps[0]
    assert sr.status == report.status == FAILED and sr.object_poll.outcome == "matched"
    assert any(not c.ok and c.point == "response" for c in sr.checks)


def test_snapshots_are_owned_and_default_repr_excludes_values(tmp_path):
    marker = "confidential-object-sentinel"
    probe = Probe(lambda q: facts(q, objects=[ports.ObservedObject(q.id, {"name": marker})]))
    report, _, _ = execute(tmp_path, probe, steps=[waiting(checks=[check("name", marker)])])
    sr = report.domains[0].steps[0]
    probe.facts[0].objects[0].fields["name"] = "mutated"
    assert sr.state_observations[0].objects[0].fields == {"name": marker}
    assert marker not in repr(report) and marker not in repr(sr.object_poll)
    assert {f.name for f in fields(ObjectPollResult)} == {"timeout", "interval", "attempts", "elapsed", "outcome"}


@pytest.mark.parametrize("payload", [{}, {"id": None}, {"id": False}, {"id": []}, {"id": ""}])
def test_bad_dynamic_id_blocks_before_business_action(tmp_path, payload):
    raw = waiting(checks=[absent(identity={"from_step": "create", "response_field": "id"})])
    api = FakeApi({("POST", "create"): {"json": {"success": True, "data": payload}}})
    report, _, _ = execute(tmp_path, Probe(facts), steps=[flow_request("create"), raw], api=api)
    first, second = report.domains[0].steps
    assert first.status == PASSED and second.status == BLOCKED
    assert second.object_poll is None and len(api.sent) == 1


def test_conflicting_dynamic_selectors_block_before_business_action(tmp_path):
    raw = waiting(checks=[absent(identity={"from_step": "create", "response_field": "id"}),
                         absent(identity={"from_step": "create", "response_field": "other"})])
    api = FakeApi({("POST", "create"): {"json": {"success": True, "data": {"id": 22, "other": "22"}}}})
    probe = Probe(facts)
    report, _, _ = execute(tmp_path, probe, steps=[flow_request("create"), raw], api=api)
    second = report.domains[0].steps[1]
    assert second.status == BLOCKED and second.blocked_by == ["create"]
    assert len(api.sent) == 1 and not probe.queries


def test_no_policy_retains_one_shot_behavior(tmp_path):
    raw = waiting()
    del raw["object_poll"]
    probe = Probe(lambda q: facts(q, count=int(len(probe.queries) == 1)))
    report, _, clock = execute(tmp_path, probe, steps=[raw])
    assert report.status == FAILED and len(probe.queries) == 1 and not clock.sleeps
    assert report.domains[0].steps[0].object_poll is None


def test_live_ui_action_runs_once_and_failed_ui_is_not_erased(tmp_path):
    raw = ui_step()
    raw["object_poll"] = {"on_timeout": "FAIL"}
    raw["expect"]["ui"][0]["anchor"] = "missing"
    probe = Probe(lambda q: facts(q, objects=[ports.ObservedObject(q.id, {"name": "actual-name"})]))
    ui = ScriptedUi(1)
    report, _, _ = execute(tmp_path, probe, steps=[raw], projection="e2e", ui=ui)
    sr = report.domains[0].steps[0]
    assert sr.status == FAILED and sr.object_poll.outcome == "matched"
    assert len(ui.permits) == 1 and ui.open_calls == ui.close_calls == 1
    assert len(report.domains[0].provider_recordings) == 1


def test_frontend_does_not_query_or_claim_object_poll(tmp_path):
    raw = ui_step()
    raw["object_poll"] = {"on_timeout": "FAIL"}
    probe = Probe(lambda q: pytest.fail("mock must not observe storage"))
    path = write(tmp_path, [raw])
    ui = ScriptedUi(1)
    report = run_scenario(path, adapters(probe, ui=ui), projections=("frontend",), mock_plan=ui.plan())
    sr = report.domains[0].steps[0]
    assert not probe.queries and sr.object_poll is None
    assert any("backend_state" in reason for reason in sr.not_checked)


def test_contract_reuses_single_response_and_never_claims_object_poll(tmp_path):
    path = write(tmp_path, [waiting()])
    probe, clock = Probe(facts), RecordingClock()
    report = run_scenario(path, adapters(probe), projections=("backend", "contract"),
                         poll_config=PollConfig(2, .5), now=clock.now, sleep=clock.sleep)
    assert report.status == PASSED and len(probe.queries) == 1
    contract_result = report.domains[1]
    assert any("object_poll" in reason for reason in contract_result.not_checked)
    assert all(step.object_poll is None and not step.state_observations for step in contract_result.steps)


def test_one_level_include_executes_named_leaf_once(tmp_path):
    child_raw = waiting(checks=[absent(identity={"from_parameter": "record_id"})])
    child = document(child_raw)
    child["scenario"] = "shared.wait"
    root = document({"id": "included", "do": {"include": "shared.wait"}})
    path, _ = write_bundle(tmp_path, root, child)
    probe, clock = Probe(facts), RecordingClock()
    ad = adapters(probe)
    report = run_scenario(path, ad, projections=("backend",),
        poll_config=PollConfig(2, .5), now=clock.now, sleep=clock.sleep)
    assert report.status == PASSED and len(ad.api.sent) == 1
    assert probe.queries[0].step_id == "included/remove"
    assert report.domains[0].steps[0].object_poll.outcome == "matched"


def test_flow_does_not_publish_writes_after_object_timeout(tmp_path):
    raw = waiting(checks=[absent(identity={"from_parameter": "record_id"})])
    path = flow_path(tmp_path, [
        flow_scenario("writer", [raw], parameters={"record_id": 22},
                      writes={"id": {"from_parameter": "record_id"}}),
        flow_scenario("reader", [flow_request("read", body={"id": {"from_flow": "id"}})])],
        parameters={"id": {}})
    probe, clock = Probe(lambda q: facts(q, count=1)), RecordingClock()
    ad = adapters(probe)
    report = run_flow(path, ad, projections=("backend",),
        poll_config=PollConfig(2, .5), now=clock.now, sleep=clock.sleep)
    assert report.status == FAILED and len(ad.api.sent) == 1
    assert report.scenarios[0].domains[0].steps[0].object_poll.outcome == "timeout"
    assert report.scenarios[1].domains[0].steps[0].status == BLOCKED


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("policy", [False, PollPolicy("SKIP"), {"on_timeout": "FAIL"}])
def test_direct_model_bad_policy_is_refused_before_auth_or_action(tmp_path, projection, policy):
    path = write(tmp_path, [waiting()])
    scenario = load_scenario(path)
    scenario.steps[0].object_poll = policy
    ad = adapters(Probe(facts))
    def forbidden(*args):
        pytest.fail("invalid model must not reach an action port")
    ad.auth.identify = forbidden
    options = dict(auth=ad.auth, api=ad.api, state=None, recorder=FakeRecorder(),
                   resolve_request=ad.resolve_request, normalizer=FakeNormalizer(), object_state=ad.object_state)
    domain = backend.run(scenario, **options) if projection == "backend" else e2e.run(scenario, ui=None, **options)
    assert domain.steps[0].status == ERROR and not ad.api.sent and not ad.object_state.queries


@pytest.mark.parametrize("projections", [("backend",), ("e2e",), ("backend", "contract")])
def test_distinct_generated_parameter_ids_block_without_prior_step_source(tmp_path, projections):
    raw = waiting(checks=[absent(identity={"from_parameter": "first"}),
                         absent(identity={"from_parameter": "second"})])
    path = write(tmp_path, [raw], parameters={"first": {"from_run": "unique"},
                                             "second": {"from_run": "unique"}})
    probe, ad = Probe(facts), adapters()
    ad.object_state = probe
    report = run_scenario(path, ad, projections=projections)
    assert report.status == DEGRADED and not report.passed
    assert all(domain.steps[0].status == BLOCKED for domain in report.domains)
    assert not ad.api.sent and not probe.queries
    assert report.domains[0].steps[0].object_poll is None


def test_contract_rejects_empty_block_reason_when_object_ids_do_not_conflict(tmp_path):
    from refracto.projection import contract
    from refracto.report import StepResult
    path = write(tmp_path, [waiting()])
    scenario = load_scenario(path)
    result = contract.run(scenario, [], FakeNormalizer(), execution_steps=[
        StepResult("remove", BLOCKED, blocked_by=[])])
    assert result.steps[0].status == ERROR
