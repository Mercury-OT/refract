"""Shared values require successful Scenario evidence and retain exact identity."""
import hashlib
import json

import pytest

from refracto import ports
from refracto.runner import Adapters, run_flow
from tests.fakes import FakeAuth, FakeApi, FakeNormalizer, FakeRecorder


def request(sid, *, path=None, body=None, response=None, **options):
    result = {"id": sid, "do": {"request": {"method": "POST", "path": path or [sid]}},
              "expect": {"response": [{"check": "success"}] if response is None else response}}
    if body is not None:
        result["do"]["request"]["body"] = body
    result.update(options)
    return result


def scenario(sid, steps, *, writes=None, parameters=None):
    result = {"schema_version": 1, "scenario": sid, "users": ["actor"], "steps": steps}
    if writes is not None:
        result["write_flow"] = writes
    if parameters is not None:
        result["parameters"] = parameters
    return result


def flow_path(tmp_path, documents, *, parameters=None, policy=None, repeat=None):
    entries, nodes = {}, []
    for index, document in enumerate(documents):
        path = tmp_path / f"source-{index}.yaml"
        path.write_text(json.dumps(document))
        entries[document["scenario"]] = {"path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for index, sid in enumerate(repeat or [doc["scenario"] for doc in documents]):
        nodes.append({"id": f"n{index}", "scenario": sid, "with_users": {"actor": "owner"}})
    raw = {"schema_version": 1, "flow": "synthetic.lifecycle", "users": ["owner"],
           "parameters": parameters or {}, "scenarios": nodes}
    if policy is not None:
        raw["on_failure"] = policy
    path = tmp_path / "flow.yaml"
    path.write_text(json.dumps(raw))
    path.with_suffix(".scenarios.json").write_text(json.dumps({"manifest_version": 1, "scenarios": entries}))
    return path


class TrackingAuth(FakeAuth):
    def __init__(self):
        self.identifications, self.sessions = [], []

    def identify(self, user):
        self.identifications.append(user)
        return super().identify(user)

    def session(self, user):
        self.sessions.append(user)
        return ports.UserSession(principal_id="fake-principal:" + user,
                                 authentication_id=str(len(self.sessions)), credentials={"user": user})


def adapters(responses=None, *, api=None, recorder=FakeRecorder):
    return Adapters(TrackingAuth(), api or FakeApi(responses), None, None, recorder,
        lambda action: ports.RequestSpec(action.method, action.path, body=action.body,
                                        query=action.query or {}, headers=action.headers or {}),
        FakeNormalizer())


def field(name, value):
    return {"check": "field_equals", "field": name, "value": value}


def test_boundary_snapshots_atomic_copy_and_contract_replay(tmp_path):
    path = flow_path(tmp_path, [
        scenario("writer", [request("write", body={"name": {"from_flow": "name"}},
            response=[field("seen", {"from_flow": "name"})]),
            request("still_old", body={"name": {"from_flow": "name"}})],
            writes={"name": {"from_step": "write", "response_field": "next"},
                    "previous": {"from_flow": "name"}}),
        scenario("reader", [request("read", body={"name": {"from_flow": "name"},
                                                   "previous": {"from_flow": "previous"}},
            response=[field("seen", {"from_flow": "name"})])]),
    ], parameters={"name": {"initial": "private-old"}, "previous": {}})
    ad = adapters({("POST", "write"): {"json": {"success": True, "data": {
        "seen": "private-old", "next": "private-new"}}},
        ("POST", "read"): {"json": {"success": True, "data": {"seen": "private-new"}}}})
    report = run_flow(path, ad, projections=("backend", "contract"))
    assert report.status == "PASSED", report.localize()
    assert [item.body for item in ad.api.sent] == [{"name": "private-old"}, {"name": "private-old"},
                                                {"name": "private-new", "previous": "private-old"}]
    assert ad.auth.sessions == ["owner"]
    assert [(item.node_id, item.scenario_id) for item in report.scenarios] == [("n0", "writer"), ("n1", "reader")]
    first, second = [item.domains[0] for item in report.scenarios]
    assert first.flow_reads["name"].version == 0
    assert first.flow_writes["name"].version == second.flow_reads["name"].version == 1
    assert first.flow_writes["name"].response_origin.step_id == "n0/write"
    assert first.flow_writes["previous"].source_version == 0
    assert report.scenarios[1].domains[1].flow_reads == second.flow_reads
    assert report.source_pins["scenarios"]["writer"]["sha256"]
    assert "private-old" not in repr(report) and "private-new" not in repr(report)
    assert run_flow(path, adapters(ad.api.responses), projections=("backend",)).run_id != report.run_id


@pytest.mark.parametrize("missing", [False, True])
def test_unsuccessful_multiwrite_invalidates_every_destination_without_stale_fallback(tmp_path, missing):
    path = flow_path(tmp_path, [
        scenario("writer", [request("write", response=[{"check": "success"}])],
            writes={"left": {"from_step": "write", "response_field": "left"},
                    "right": {"from_step": "write", "response_field": "missing" if missing else "right"}}),
        scenario("reader", [request("dependent", body={"value": {"from_flow": "left"}}),
                             request("independent", body={"value": {"from_flow": "untouched"}}),
                             request("other", body={"value": {"from_flow": "right"}})]),
    ], parameters={"left": {"initial": "obsolete-left"}, "right": {"initial": "obsolete-right"},
                   "untouched": {"initial": "retained"}}, policy="continue")
    ad = adapters({("POST", "write"): {"json": {"success": missing,
                                              "data": {"left": "fresh-left", "right": "fresh-right"}}}})
    report = run_flow(path, ad, projections=("backend", "contract"))
    assert report.status == "FAILED"
    assert [item.path for item in ad.api.sent] == ["write", "independent"]
    first, second = [item.domains[0] for item in report.scenarios]
    assert [item.status for item in second.steps] == ["BLOCKED", "PASSED", "BLOCKED"]
    assert all(not item.available for item in first.flow_writes.values())
    assert all(second.flow_reads[name].version == 1 for name in ("left", "right"))
    assert second.flow_reads["untouched"].version == 0
    assert report.scenarios[1].domains[1].status == "DEGRADED"
    if missing:
        assert first.steps[-1].step_id == "@flow-write:n0" and first.steps[-1].status == "ERROR"
    else:
        assert second.steps[1].after_failures == ["n0/write"]


@pytest.mark.parametrize("kind", ["failed", "error", "empty", "degraded", "blocked"])
def test_default_boundary_stops_on_every_nonpassed_node(tmp_path, kind):
    first = request("first")
    if kind == "empty":
        first = {"id": "first", "do": "open", "target": "page", "expect": {
            "ui": [{"check": "visible", "anchor": "page"}]}}
    elif kind == "degraded":
        first["expect"]["backend_state"] = [{"check": "span_exists", "span": "work"}]
    elif kind == "blocked":
        first["do"]["request"]["body"] = {"value": {"from_flow": "unset"}}
    path = flow_path(tmp_path, [scenario("first", [first]), scenario("next", [request("next")])],
                     parameters={"unset": {}})
    ad = adapters({("POST", "first"): {"json": {"success": kind != "failed"}}})
    if kind == "error":
        ad.resolve_request = lambda _: (_ for _ in ()).throw(RuntimeError("secret"))
    report = run_flow(path, ad, projections=("backend", "contract"), sleep=lambda _: None)
    assert report.status != "PASSED"
    assert report.scenarios[1].domains[0].steps[0].status == "BLOCKED"
    assert report.scenarios[1].domains[0].flow_after_failures == ["n0"]
    assert not any(item.path == "next" for item in ad.api.sent)
    assert report.scenarios[1].domains[1].status == "DEGRADED"


def test_projection_stores_and_repeated_invocations_are_independent(tmp_path):
    path = flow_path(tmp_path, [scenario("repeated", [request("work", body={"previous": {"from_flow": "id"}})],
        writes={"id": {"from_step": "work", "response_field": "id"}})],
        parameters={"id": {"initial": "seed"}}, repeat=["repeated", "repeated"])
    class SequentialApi(FakeApi):
        def send(self, spec, session):
            self.responses[("POST", "work")] = {"json": {"success": True, "data": {"id": str(len(self.sent))}}}
            return super().send(spec, session)
    ad = adapters(api=SequentialApi())
    report = run_flow(path, ad, projections=("backend", "e2e", "contract"))
    assert report.status == "PASSED", report.localize()
    assert [item.body for item in ad.api.sent] == [
        {"previous": "seed"}, {"previous": "0"}, {"previous": "seed"}, {"previous": "2"}]
    assert ad.auth.sessions == ["owner", "owner"]
    assert [item.step_id for item in report.domains[0].steps] == ["n0/work", "n1/work"]


@pytest.mark.parametrize("initial", [None, False, 0, "", [], {}, {"from_flow": "literal-marker"}])
def test_initialized_falsy_values_are_actual_data(tmp_path, initial):
    path = flow_path(tmp_path, [scenario("copy", [request("first", body={"value": {"from_flow": "value"}})],
        writes={"copy": {"from_flow": "value"}}), scenario("read", [request("second", body={
            "value": {"from_flow": "copy"}})])], parameters={"value": {"initial": initial}, "copy": {}})
    ad = adapters()
    report = run_flow(path, ad, projections=("backend",))
    assert report.status == "PASSED"
    assert all(item.body == {"value": initial} for item in ad.api.sent)


def test_recorder_failure_invalidates_final_writes_and_retains_error(tmp_path):
    path = flow_path(tmp_path, [scenario("write", [request("work")], writes={"value": {
        "from_step": "work", "response_field": "value"}})], parameters={"value": {}})
    class BrokenRecorder(FakeRecorder):
        def responses(self):
            raise RuntimeError("recorder unavailable")
    ad = adapters({("POST", "work"): {"json": {"success": True, "data": {"value": "observed"}}}},
                  recorder=BrokenRecorder)
    report = run_flow(path, ad, projections=("backend", "contract"))
    assert report.status == "FAILED"
    assert report.scenarios[0].domains[0].steps[-1].status == "ERROR"
    assert not report.scenarios[0].domains[0].flow_writes["value"].available


def test_one_clock_and_per_invocation_projection_unique_values(tmp_path):
    document = scenario("unique", [request("work", body={"token": {"from_parameter": "token"},
        "time": {"from_parameter": "time"}})], parameters={"token": {"from_run": "unique"},
        "time": {"from_run": "time"}}, writes={"token": {"from_parameter": "token"}})
    path = flow_path(tmp_path, [document], parameters={"token": {}}, repeat=["unique", "unique"])
    ad = adapters()
    report = run_flow(path, ad, projections=("backend", "e2e", "contract"),
                      run_time="2026-11-01T01:02:03.004Z")
    assert report.status == "PASSED"
    assert len({item.body["token"] for item in ad.api.sent}) == 4
    assert {item.body["time"] for item in ad.api.sent} == {"2026-11-01T01:02:03.004Z"}
    assert report.run_unique_values["contract"] == report.run_unique_values["backend"]


def test_missing_ui_and_contract_only_fail_before_live_actions(tmp_path):
    path = flow_path(tmp_path, [scenario("one", [request("work")])])
    ad = adapters()
    with pytest.raises(ValueError, match="UiDriver"):
        run_flow(path, ad, projections=("backend", "frontend"))
    with pytest.raises(ValueError, match="backend"):
        run_flow(path, ad, projections=("contract",))
    assert not ad.api.sent and not ad.auth.sessions


@pytest.mark.parametrize("replace_existing", [False, True])
@pytest.mark.parametrize("explicit_new", [False, True])
def test_failed_authentication_cannot_retry_or_reuse_old_session_implicitly(tmp_path, replace_existing, explicit_new):
    documents = ([scenario("initial", [request("initial")])] if replace_existing else [])
    documents.extend([scenario("broken", [request("broken", **({"session": "new"} if replace_existing else {}))]),
                      scenario("later", [request("later", **({"session": "new"} if explicit_new else {}))])])
    path = flow_path(tmp_path, documents, policy="continue")
    class FailedAcquisition(TrackingAuth):
        attempts = 0
        def session(self, user):
            self.attempts += 1
            if self.attempts == (2 if replace_existing else 1):
                raise RuntimeError("sensitive authentication failure")
            return super().session(user)
    ad = adapters()
    ad.auth = FailedAcquisition()
    report = run_flow(path, ad, projections=("backend",))
    assert [item.status for item in report.domains[0].steps] == (
        (["PASSED"] if replace_existing else []) + ["ERROR", "PASSED" if explicit_new else "ERROR"])
    assert ad.auth.attempts == (1 + int(replace_existing) + int(explicit_new))
    assert report.scenarios[-1].domains[0].flow_after_failures == ["n1" if replace_existing else "n0"]
    assert [item.path for item in ad.api.sent] == (
        (["initial"] if replace_existing else []) + (["later"] if explicit_new else []))


def test_skip_poll_boundary_cannot_publish_or_continue_by_default(tmp_path):
    from refracto.runner import PollConfig
    first = request("poll", poll={"on_timeout": "SKIP"})
    first["do"]["request"]["method"] = "GET"
    path = flow_path(tmp_path, [scenario("poller", [first], writes={"value": {
        "from_step": "poll", "response_field": "value"}}), scenario("later", [request("later")])],
        parameters={"value": {"initial": "old"}})
    ad = adapters({("GET", "poll"): {"json": {"success": False, "data": {"value": "unready"}}}})
    clock = [0.0]
    def sleep(duration):
        clock[0] += duration
    report = run_flow(path, ad, projections=("backend",), poll_config=PollConfig(.1, .1),
                      now=lambda: clock[0], sleep=sleep)
    assert [item.status for item in report.domains[0].steps] == ["SKIPPED", "BLOCKED"]
    assert report.status == "DEGRADED"
    assert not report.scenarios[0].domains[0].flow_writes["value"].available
    history = report.parameter_history["backend"]["value"]
    assert [item.provenance.available for item in history] == [True, False]
    assert history[0].value == "old"
    assert "old" not in repr(history)


def test_final_recorder_read_failure_is_visible_after_prior_publication(tmp_path):
    documents = [scenario("first", [request("first")], writes={"value": {
        "from_step": "first", "response_field": "value"}}), scenario("last", [request("last")], writes={"value": {
        "from_step": "last", "response_field": "value"}})]
    path = flow_path(tmp_path, documents, parameters={"value": {}})
    class FinalReadFailure(FakeRecorder):
        reads = 0
        def responses(self):
            self.reads += 1
            if self.reads == 3:
                raise RuntimeError("unavailable")
            return super().responses()
    ad = adapters({("POST", name): {"json": {"success": True, "data": {"value": name}}}
                   for name in ("first", "last")}, recorder=FinalReadFailure)
    report = run_flow(path, ad, projections=("backend", "contract"))
    assert report.status == "FAILED"
    assert report.scenarios[-1].domains[0].steps[-1].step_id == "_recorder"
    assert not report.scenarios[-1].domains[0].flow_writes["value"].available
    assert report.scenarios[0].domains[0].flow_writes["value"].available


@pytest.mark.parametrize("consumer", ["direct", "alias", "concat"])
def test_invalid_available_flow_value_blocks_consumer_without_stopping_independent_leaf(tmp_path, consumer):
    parameter = {"alias": {"from_flow": "value"}}
    used = {"from_flow": "value"} if consumer == "direct" else {"from_parameter": "alias"}
    if consumer == "concat":
        parameter["alias"] = {"concat": ["prefix", {"from_flow": "value"}]}
    path = flow_path(tmp_path, [scenario("invalid", [request("dependent", path=["items", used]),
        request("independent")], parameters=parameter)], parameters={"value": {"initial": False}})
    ad = adapters()
    report = run_flow(path, ad, projections=("backend", "contract"))
    backend = report.scenarios[0].domains[0]
    assert [item.status for item in backend.steps] == ["BLOCKED", "PASSED"]
    assert backend.steps[0].blocked_by == ["flow:value"]
    assert [item.path for item in ad.api.sent] == ["independent"]
    assert report.scenarios[0].domains[1].status == "DEGRADED"
