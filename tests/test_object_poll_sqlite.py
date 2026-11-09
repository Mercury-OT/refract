"""A real asynchronous writer and independent fresh committed SQLite reads."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sqlite3
from threading import Event
import time

import pytest
import yaml

from adapters.sqlite_records.adapter import SQLiteRecordProbe, build_adapters
from examples.sqlite_records.async_app import AsyncRecordsApp
from examples.sqlite_records.app import RecordsApp, Response
from examples.sqlite_records.run_async import main
from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.runner import PollConfig, run_scenario


SCENARIO = (Path(__file__).resolve().parents[1] / "examples/sqlite_records/scenarios"
            / "create_verify_async_delete.yaml")


class ControlledApp(AsyncRecordsApp):
    """The host schedules the worker; the probe never drives business state."""

    def __init__(self, database, fault=None):
        super().__init__(database)
        self.release = Event()
        self.fault = fault

    def _before_delete(self):
        while not self._cancel.is_set():
            if self.release.wait(0.02):
                return not self._cancel.is_set()
        return False

    def _commit_delete(self, connection, record_id):
        if self.fault == "no-op":
            return
        if self.fault == "uncommitted":
            connection.execute("DELETE FROM entries WHERE record_id = ?", (record_id,))
            return
        super()._commit_delete(connection, record_id - 1 if self.fault == "wrong-id" else record_id)

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if self.fault == "response" and method == "DELETE" and response.status == 202:
            return Response(500, {"error": "synthetic_response_failure"})
        return response

    def finish_worker(self):
        self.release.set()
        for thread in self._workers:
            thread.join(timeout=2)
        assert all(not thread.is_alive() for thread in self._workers)
        assert self.worker_errors == []


class Clock:
    def __init__(self, callback=None):
        self.elapsed = 0.0
        self.sleeps = []
        self.callback = callback

    def now(self):
        return self.elapsed

    def sleep(self, duration):
        self.sleeps.append(duration)
        if self.callback:
            self.callback()
        self.elapsed += duration


class AuditedProbe(SQLiteRecordProbe):
    def __init__(self, app, fault=None):
        super().__init__(app.database)
        self.app = app
        self.fault = fault
        self.connections = []
        self.statements = []
        self.action_counts = []

    def _connect(self):
        connection = super()._connect()
        self.connections.append(connection)
        assert connection is not self.app.connection
        assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        connection.set_trace_callback(self.statements.append)
        if self.fault == "query-failure" and len(self.app.requests) == 3:
            connection.set_authorizer(lambda *args: sqlite3.SQLITE_DENY)
        return connection

    def observe_object(self, query):
        self.action_counts.append(len(self.app.requests))
        facts = super().observe_object(query)
        if self.fault == "always-empty":
            return replace(facts, objects=[])
        if self.fault == "incomplete" and query.fields == ():
            return replace(facts, complete=False)
        return facts


def assert_closed(probe):
    assert len({id(connection) for connection in probe.connections}) == len(probe.connections)
    for connection in probe.connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def run(app, probe, clock, projection, path=SCENARIO):
    return run_scenario(path, build_adapters(app, probe=probe), projections=(projection,),
                        poll_config=PollConfig(timeout=0.3, interval=0.1),
                        now=clock.now, sleep=clock.sleep)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_async_deletion_passes_after_positive_existence_control(tmp_path, projection):
    with ControlledApp(tmp_path / "async.sqlite") as app:
        probe = AuditedProbe(app)
        clock = Clock(app.finish_worker)
        report = run(app, probe, clock, projection)
        domain = report.domains[0]
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        assert [step.status for step in domain.steps] == ["PASSED"] * 3
        assert [record.status for record in domain.provider_recordings] == [201, 200, 202]
        created = domain.provider_recordings[0].json
        assert [(method, path) for method, path, _, _ in app.requests] == [
            ("POST", "/records"), ("GET", f"/records/{created['id']}"),
            ("DELETE", f"/records/{created['id']}")]
        step = domain.steps[-1]
        assert step.attempts == 1
        assert step.object_poll.attempts == 2 and step.object_poll.outcome == "matched"
        assert step.object_poll.timeout == 0.3 and step.object_poll.interval == 0.1
        assert step.object_poll.elapsed == pytest.approx(0.1)
        assert clock.sleeps == [0.1]
        assert len(step.state_observations) == 2
        assert len(step.state_observations[0].objects) == 1
        assert step.state_observations[0].objects[0].fields == {}
        assert step.state_observations[1].objects == []
        assert all(check.ok for check in step.checks)
        assert probe.action_counts == [2, 3, 3]
        assert len({q.observation_id for q in probe.queries}) == 3
        assert [q.fields for q in probe.queries] == [("code",), (), ()]
        assert all(q.id == created["id"] and q.projection == projection
                   and q.user == "creator" and q.session_generation == 1 for q in probe.queries)
        assert len(probe.statements) == 3 and all(sql.startswith("SELECT ") for sql in probe.statements)
        assert app.connection.execute("SELECT record_id FROM entries").fetchall() == []
        assert_closed(probe)
    assert all(not thread.is_alive() for thread in app._workers)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("fault", ["no-op", "uncommitted", "wrong-id"])
def test_accepted_but_surviving_record_times_out_without_retrying_delete(tmp_path, projection, fault):
    with ControlledApp(tmp_path / "surviving.sqlite", fault) as app:
        if fault == "wrong-id":
            app.connection.execute("INSERT INTO entries (business_code, label) VALUES (?, ?)",
                                   ("other-code", "Other record"))
            app.connection.commit()
        probe = AuditedProbe(app)
        clock = Clock(app.finish_worker)
        report = run(app, probe, clock, projection)
        domain = report.domains[0]
        step = domain.steps[-1]
        created_id = domain.provider_recordings[0].json["id"]
        assert report.status == "FAILED" and step.status == "FAILED"
        assert step.object_poll.outcome == "timeout" and step.object_poll.attempts == 3
        assert step.object_poll.elapsed == pytest.approx(0.3)
        assert step.attempts == 1 and len(app.requests) == 3
        assert len(probe.queries) == 4 and probe.action_counts == [2, 3, 3, 3]
        assert all(len(facts.objects) == 1 and facts.objects[0].id == created_id
                   for facts in step.state_observations)
        assert any(not check.ok and check.point == "backend_state" for check in step.checks)
        assert app.connection.execute("SELECT record_id FROM entries").fetchall() == [(created_id,)]
        assert_closed(probe)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("fault", ["query-failure", "incomplete"])
def test_acquisition_failure_stops_immediately_without_retry_or_sleep(tmp_path, projection, fault):
    with ControlledApp(tmp_path / "unavailable.sqlite") as app:
        probe = AuditedProbe(app, fault)
        clock = Clock(app.finish_worker)
        report = run(app, probe, clock, projection)
        step = report.domains[0].steps[-1]
        assert report.status == "FAILED" and step.status == "ERROR"
        assert step.object_poll.outcome == "error" and step.object_poll.attempts == 1
        assert len(app.requests) == 3 and len(probe.queries) == 2 and clock.sleeps == []
        assert not any(check.check == "object_absent" and check.ok for check in step.checks)
        assert str(app.database) not in step.detail and "not authorized" not in step.detail
        assert_closed(probe)
    assert all(not thread.is_alive() for thread in app._workers)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_positive_existence_control_rejects_always_empty_reader(tmp_path, projection):
    with ControlledApp(tmp_path / "positive.sqlite") as app:
        probe = AuditedProbe(app, "always-empty")
        report = run(app, probe, Clock(app.finish_worker), projection)
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED"]
        assert report.status == "FAILED" and len(app.requests) == 2 and len(probe.queries) == 1
        assert app._workers == []
        assert_closed(probe)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_eventual_absence_cannot_erase_a_failed_response(tmp_path, projection):
    with ControlledApp(tmp_path / "response.sqlite", "response") as app:
        probe = AuditedProbe(app)
        report = run(app, probe, Clock(app.finish_worker), projection)
        step = report.domains[0].steps[-1]
        assert report.status == "FAILED" and step.status == "FAILED"
        assert step.object_poll.outcome == "matched" and step.object_poll.attempts == 2
        assert any(not check.ok and check.point == "response" for check in step.checks)
        assert any(check.ok and check.check == "object_absent" for check in step.checks)
        assert app.connection.execute("SELECT record_id FROM entries").fetchall() == []
        assert len(app.requests) == 3


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_without_policy_the_same_delayed_target_still_uses_one_observation(tmp_path, projection):
    document = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    del document["steps"][-1]["object_poll"]
    path = tmp_path / "one-shot.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with ControlledApp(tmp_path / "one-shot.sqlite") as app:
        probe = AuditedProbe(app)
        clock = Clock(app.finish_worker)
        report = run(app, probe, clock, projection, path)
        step = report.domains[0].steps[-1]
        assert report.status == "FAILED" and step.status == "FAILED"
        assert step.object_poll is None and len(step.state_observations) == 1
        assert len(app.requests) == 3 and len(probe.queries) == 2 and clock.sleeps == []
        assert app.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (1,)
        assert_closed(probe)


def test_actual_busy_timeout_closes_failed_read_and_later_reads_see_new_commit(tmp_path):
    with RecordsApp(tmp_path / "bounded.sqlite") as app:
        app.connection.execute("INSERT INTO entries (business_code, label) VALUES (?, ?)",
                               ("actual-code", "Actual record"))
        app.connection.commit()
        probe = AuditedProbe(app)
        query = ports.ObjectStateQuery(observation_id="read-1", projection="backend", step_id="read",
            trace_id="trace", user="creator", session_generation=1, object="record", id=1, fields=())
        app.connection.execute("BEGIN EXCLUSIVE")
        start = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            probe.observe_object(query)
        elapsed = time.monotonic() - start
        # The driver has a one-second busy timeout, not a hard scheduler deadline.
        assert 0.8 <= elapsed < 10
        assert_closed(probe)
        app.connection.rollback()
        assert len(probe.observe_object(replace(query, observation_id="read-2")).objects) == 1
        app.connection.execute("DELETE FROM entries WHERE record_id = 1")
        app.connection.commit()
        assert probe.observe_object(replace(query, observation_id="read-3")).objects == []
        assert_closed(probe)


def test_async_example_runner_uses_real_worker_and_removes_resources(capsys):
    assert main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "PASSED", "create PASSED", "verify_exists PASSED", "delete PASSED"]


def test_async_example_preserves_approved_policy_and_single_write_structure():
    document = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1 and document["users"] == ["creator"]
    assert [step["id"] for step in document["steps"]] == ["create", "verify_exists", "delete"]
    delete = document["steps"][-1]
    identity = {"from_step": "create", "response_field": "id"}
    assert delete["do"] == {"request": {"method": "DELETE", "path": ["records", identity]}}
    assert delete["object_poll"] == {"on_timeout": "FAIL"}
    assert delete["expect"] == {"response": [{"check": "status_equals", "value": 202}],
        "backend_state": [{"check": "object_absent", "object": "record", "id": deepcopy(identity)}]}
    assert document["steps"][0]["on_failure"] == document["steps"][1]["on_failure"] == "stop"
    assert load_scenario(SCENARIO).steps[-1].object_poll.on_timeout == "FAIL"
