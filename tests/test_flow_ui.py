"""Flows retain projection-owned UI state across separately pinned Scenarios."""
import copy
import hashlib
import json

import pytest
import yaml

from refracto import ports
from refracto.runner import Adapters, run_flow
from tests.fakes import FakeNormalizer, FakeRecorder
from tests.test_users_sessions_core import Auth
from tests.ui_support import ScriptedUi, rendered, response


def click(sid, *, user=None, status=200, value="alpha", session=None):
    step = {"id": sid, "do": "click", "target": "submit", "expect": {
        "request": {"method": "POST", "path": ["items"], "body": {"name": value}},
        "response": [{"check": "status_equals", "value": status}],
    }}
    if user is not None:
        step["user"] = user
    if session is not None:
        step["session"] = session
    return step


def scenario(sid, steps, *, users=None, write_flow=None):
    document = {"schema_version": 1, "scenario": sid,
                "users": ["actor"] if users is None else users, "steps": steps}
    if write_flow is not None:
        document["write_flow"] = write_flow
    return document


def flow_path(tmp_path, documents, *, users=None, mappings=None, parameters=None,
              on_failure=None):
    """Write public synthetic sources and their exact local content pins."""
    nodes, entries = [], {}
    for index, document in enumerate(documents):
        path = tmp_path / f"scenario-{index}.yaml"
        path.write_text(yaml.safe_dump(json.loads(json.dumps(document)), sort_keys=False))
        entries[document["scenario"]] = {
            "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        nodes.append({"id": f"node{index}", "scenario": document["scenario"],
                      "with_users": mappings[index] if mappings is not None else {"actor": "owner"}})
    raw = {"schema_version": 1, "flow": "synthetic.ui_flow",
           "users": ["owner"] if users is None else users,
           "parameters": parameters or {}, "scenarios": nodes}
    if on_failure is not None:
        raw["on_failure"] = on_failure
    path = tmp_path / "flow.yaml"
    path.write_text(yaml.safe_dump(json.loads(json.dumps(raw)), sort_keys=False))
    path.with_suffix(".scenarios.json").write_text(json.dumps({
        "manifest_version": 1, "scenarios": entries}))
    return path


class ObservedUi(ScriptedUi):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opened, self.used, self.closed = [], [], []

    def open_stepwise(self, *args, **kwargs):
        context = super().open_stepwise(*args, **kwargs)
        self.opened.append(context)
        return context

    def perform_step(self, context, permit, **kwargs):
        self.used.append(context)
        return super().perform_step(context, permit, **kwargs)

    def close_stepwise(self, context):
        assert not any(previous is context for previous in self.closed)
        self.closed.append(context)
        super().close_stepwise(context)


def execute(path, ui, *, projection="e2e", auth=None):
    auth = Auth() if auth is None else auth
    adapters = Adapters(auth, None, None, ui, FakeRecorder, None, FakeNormalizer())
    report = run_flow(path, adapters, projections=(projection,),
                      mock_plan=ui.plan() if projection == "frontend" else None)
    return report, auth


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
@pytest.mark.parametrize("reader", ["peer", "anonymous"])
def test_mapped_users_keep_context_credentials_and_one_queue_between_nodes(tmp_path, projection, reader):
    mapping = {"creator": "owner", "reader": reader}
    path = flow_path(tmp_path, [
        scenario("ui.first", [click("owner", user="creator"), click("reader", user="reader")],
                 users=["creator", "reader"]),
        scenario("ui.second", [click("reader", user="reader"), click("owner", user="creator")],
                 users=["creator", "reader"]),
    ], users=["owner", reader], mappings=[mapping, mapping])
    ui = ObservedUi(4)
    report, auth = execute(path, ui, projection=projection)
    assert report.status == "PASSED", report.localize()
    assert auth.identified == auth.authenticated == (["owner"] if reader == "anonymous" else ["owner", "peer"])
    assert len(ui.opened) == len(ui.closed) == 2
    assert ui.used[0] is ui.used[3] and ui.used[1] is ui.used[2]
    assert ui.used[0] is not ui.used[1]
    expected = ["owner", None if reader == "anonymous" else reader,
                None if reader == "anonymous" else reader, "owner"]
    steps = report.domains[0].steps
    assert [step.user for step in steps] == expected
    assert [step.session_generation for step in steps] == [0 if user is None else 1 for user in expected]
    assert len({permit.execution_id for permit in ui.permits}) == 1
    assert len({permit.action_id for permit in ui.permits}) == len(ui.permits)
    assert all(not hasattr(permit, "expect") and not hasattr(permit, "flow_parameters") for permit in ui.permits)
    if projection == "frontend":
        assert ui.opened[0]["mock_queue"] is ui.opened[1]["mock_queue"]
        assert [item["fixture_id"] for item in report.domains[0].mock_consumption] == [
            "f0-0", "f1-0", "f2-0", "f3-0"]
    else:
        assert [(item.user, item.session_generation) for item in report.domains[0].provider_recordings] == [
            (user, 0 if user is None else 1) for user in expected]


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_explicit_session_new_replaces_only_that_user_at_the_next_node(tmp_path, projection):
    users = ["owner", "peer"]
    mapping = {user: user for user in users}
    path = flow_path(tmp_path, [
        scenario("ui.first", [click("owner", user="owner"), click("peer", user="peer")], users=users),
        scenario("ui.second", [click("owner", user="owner", session="new"),
                               click("peer", user="peer")], users=users),
    ], users=users, mappings=[mapping, mapping])
    ui = ObservedUi(4)
    report, auth = execute(path, ui, projection=projection)
    assert report.status == "PASSED", report.localize()
    assert auth.authenticated == ["owner", "peer", "owner"]
    assert len(ui.opened) == len(ui.closed) == 3
    assert ui.used[0] is not ui.used[2] and ui.used[1] is ui.used[3]
    assert ui.closed[0] is ui.used[0]
    assert [step.session_generation for step in report.domains[0].steps] == [1, 1, 2, 1]


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_flow_reads_are_frozen_for_whole_scenario_and_write_changes_next_node(tmp_path, projection):
    current = {"from_flow": "name"}
    first = [click("write", value=current), click("still_old", value=current)]
    for step in first:
        step["expect"]["ui"] = [{"check": "objects_matching_count", "anchor": "rows",
                                   "count": 1, "field": "name", "value": current}]
    path = flow_path(tmp_path, [
        scenario("ui.writer", first, write_flow={"name": {"from_step": "write", "response_field": "id"}}),
        scenario("ui.reader", [click("new", value=current)]),
    ], parameters={"name": {"initial": "old"}})
    requests = [[ports.RequestSpec("POST", "items", {"name": name})] for name in ("old", "old", "new")]
    ui = ObservedUi(3, requests=requests,
                    payloads=[response({"id": "new"}), response({"id": "unused"}), response()],
                    renders=[rendered("old"), rendered("old"), rendered("new")])
    report, _ = execute(path, ui, projection=projection)
    assert report.status == "PASSED", report.localize()
    assert len(ui.opened) == len(ui.closed) == 1
    assert ui.used[0] is ui.used[1] is ui.used[2]


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
@pytest.mark.parametrize("policy", [None, "continue"])
def test_failed_node_invalidates_write_and_continue_keeps_context_without_repair(tmp_path, projection, policy):
    path = flow_path(tmp_path, [
        scenario("ui.failed", [click("failed", status=201)],
                 write_flow={"name": {"from_step": "failed", "response_field": "id"}}),
        scenario("ui.independent", [click("independent")]),
        scenario("ui.dependent", [click("dependent", value={"from_flow": "name"})]),
    ], parameters={"name": {"initial": "stale"}}, on_failure=policy)
    ui = ObservedUi(3)
    report, auth = execute(path, ui, projection=projection)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == (
        ["FAILED", "PASSED", "BLOCKED"] if policy == "continue" else ["FAILED", "BLOCKED", "BLOCKED"])
    assert auth.authenticated == ["owner"]
    assert len(ui.opened) == len(ui.closed) == 1
    assert len(ui.permits) == (2 if policy == "continue" else 1)
    assert all(context is ui.opened[0] for context in ui.used)
    if policy == "continue":
        assert report.domains[0].steps[1].after_failures == ["node0/failed"]


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_evidence_from_previous_scenario_is_not_reaccepted(tmp_path, projection):
    path = flow_path(tmp_path, [scenario("ui.first", [click("same")]),
                                scenario("ui.second", [click("same")])])
    retained = []
    def replay(index, outcome, permit):
        if index == 0:
            retained.append(copy.deepcopy(outcome))
            return outcome
        return retained[0]
    ui = ObservedUi(2, mutate=replay)
    report, _ = execute(path, ui, projection=projection)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "ERROR"]
    assert len(ui.opened) == len(ui.closed) == 1


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_another_flow_run_creates_fresh_context_and_evidence_namespace(tmp_path, projection):
    path = flow_path(tmp_path, [scenario("ui.first", [click("same")]),
                                scenario("ui.second", [click("same")])])
    ui = ObservedUi(4)
    assert execute(path, ui, projection=projection)[0].status == "PASSED"
    # Fixture selection resets for the next run; adapter script progress does not.
    assert execute(path, ui, projection=projection)[0].status == "PASSED"
    assert len(ui.opened) == len(ui.closed) == 2
    assert ui.used[0] is ui.used[1] and ui.used[2] is ui.used[3]
    assert ui.used[0] is not ui.used[2]
    assert ui.permits[0].execution_id != ui.permits[2].execution_id
    assert ui.permits[0].context_id != ui.permits[2].context_id


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
@pytest.mark.parametrize("explicit_new", [False, True])
def test_failed_context_creation_is_not_silently_retried_by_continue(tmp_path, projection, explicit_new):
    path = flow_path(tmp_path, [
        scenario("ui.first", [click("first")]),
        scenario("ui.second", [click("second", session="new" if explicit_new else None)]),
    ], on_failure="continue")
    class FailedOpen(ObservedUi):
        attempts = 0
        def open_stepwise(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("synthetic failed context creation")
            return super().open_stepwise(*args, **kwargs)
    ui = FailedOpen(2)
    report, auth = execute(path, ui, projection=projection)
    assert [step.status for step in report.domains[0].steps] == [
        "ERROR", "PASSED" if explicit_new else "ERROR"]
    assert ui.attempts == (2 if explicit_new else 1)
    assert len(ui.opened) == len(ui.closed) == (1 if explicit_new else 0)
    assert auth.authenticated == (["owner", "owner"] if explicit_new else ["owner"])


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_action_error_continue_uses_same_context_and_does_not_reauthenticate(tmp_path, projection):
    path = flow_path(tmp_path, [scenario("ui.first", [click("first")]),
                                scenario("ui.second", [click("second")])], on_failure="continue")
    ui = ObservedUi(2, terminal=(0, "error"))
    report, auth = execute(path, ui, projection=projection)
    assert [step.status for step in report.domains[0].steps] == ["ERROR", "PASSED"]
    assert auth.authenticated == ["owner"]
    assert ui.used[0] is ui.used[1]
    assert len(ui.opened) == len(ui.closed) == 1


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_close_error_does_not_retry_cleanup_or_hide_final_node_failure(tmp_path, projection):
    path = flow_path(tmp_path, [scenario("ui.first", [click("first")]),
                                scenario("ui.second", [click("second")], write_flow={
                                    "name": {"from_step": "second", "response_field": "id"}})],
                     parameters={"name": {}})
    class FailedClose(ObservedUi):
        def close_stepwise(self, context):
            super().close_stepwise(context)
            raise RuntimeError("synthetic failed cleanup")
    ui = FailedClose(2)
    report, _ = execute(path, ui, projection=projection)
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "ERROR"]
    assert report.domains[0].steps[-1].step_id.startswith("@flow-close:")
    assert report.scenarios[-1].domains[0].flow_writes["name"].available is False
    assert report.status == "FAILED"
    assert len(ui.opened) == len(ui.closed) == 1


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_failed_explicit_replacement_does_not_create_implicit_context_later(tmp_path, projection):
    path = flow_path(tmp_path, [scenario("ui.first", [click("first")]),
                                scenario("ui.replace", [click("replace", session="new")]),
                                scenario("ui.last", [click("last")])], on_failure="continue")
    class FailedClose(ObservedUi):
        def close_stepwise(self, context):
            super().close_stepwise(context)
            raise RuntimeError("synthetic failed replacement cleanup")
    ui = FailedClose(3)
    report, auth = execute(path, ui, projection=projection)
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "ERROR", "ERROR"]
    assert auth.authenticated == ["owner", "owner"]
    assert len(ui.opened) == len(ui.closed) == len(ui.permits) == 1


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_global_ui_preflight_reports_each_leaf_once_without_opening_context(tmp_path, projection):
    path = flow_path(tmp_path, [scenario("ui.first", [click("first")]),
                                scenario("ui.second", [click("second")])])
    class UnsupportedUi(ObservedUi):
        def supports_stepwise_mode(self, mode):
            return False
    ui = UnsupportedUi(2)
    report, auth = execute(path, ui, projection=projection)
    assert [(step.step_id, step.status) for step in report.domains[0].steps] == [
        ("node0/first", "ERROR"), ("node1/second", "BLOCKED")]
    assert [step.step_id for step in report.scenarios[0].domains[0].steps] == ["node0/first"]
    assert [step.step_id for step in report.scenarios[1].domains[0].steps] == ["node1/second"]
    assert not auth.authenticated
    assert not ui.opened and not ui.closed and not ui.permits
