"""Deletion claims must agree with an independent committed SQLite lookup."""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest
import yaml

from adapters.sqlite_records.adapter import SQLiteRecordProbe, build_adapters
from examples.sqlite_records.app import RecordsApp
from examples.sqlite_records.run import main
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario


SCENARIO = (Path(__file__).resolve().parents[1] / "examples/sqlite_records/scenarios"
            / "create_verify_delete.yaml")
PROJECTIONS = [("backend",), ("e2e",)]


class AuditedProbe(SQLiteRecordProbe):
    def __init__(self, app):
        super().__init__(app.database)
        self.app = app
        self.connections = []
        self.statements = []
        self.action_counts = []
        self.hashes = []

    def _connect(self):
        connection = super()._connect()
        assert connection is not self.app.connection
        assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        self.connections.append(connection)
        connection.set_trace_callback(self.statements.append)
        return connection

    def observe_object(self, query):
        self.action_counts.append(len(self.app.requests))
        before = sha256(self.app.database.read_bytes()).hexdigest()
        facts = super().observe_object(query)
        self.hashes.append((before, sha256(self.app.database.read_bytes()).hexdigest()))
        return facts


def assert_lifecycle_reads(report, app, probe, projection):
    domain = report.domains[0]
    assert domain.projection == projection
    assert [step.step_id for step in domain.steps] == ["create", "verify_exists", "delete"]
    assert [record.status for record in domain.provider_recordings] == [201, 200, 204]
    created = domain.provider_recordings[0].json
    assert type(created["id"]) is int
    assert [(method, path) for method, path, _, _ in app.requests] == [
        ("POST", "/records"), ("GET", f"/records/{created['id']}"),
        ("DELETE", f"/records/{created['id']}")]
    assert domain.provider_recordings[-1].json is None
    assert domain.provider_recordings[-1].text == ""
    assert all(check.ok for check in domain.checks if check.point == "response")
    assert len(probe.queries) == 2
    assert probe.action_counts == [2, 3]
    assert [query.fields for query in probe.queries] == [("code",), ()]
    assert len({query.observation_id for query in probe.queries}) == 2
    for query, step in zip(probe.queries, domain.steps[1:], strict=True):
        assert query.object == "record" and query.id == created["id"]
        assert type(query.id) is int
        assert query.step_id == step.step_id and query.trace_id == step.trace_id
        assert query.projection == projection and query.user == "creator"
        assert query.session_generation == 1
        assert len(step.state_observations) == 1
        facts = step.state_observations[0]
        assert facts.query == query and facts.complete is True
        assert facts.source == "sqlite-records"
    assert len(probe.connections) == 2
    assert len(probe.statements) == 2
    assert all(statement.startswith("SELECT ") for statement in probe.statements)
    assert all(before == after for before, after in probe.hashes)
    for connection in probe.connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    positive = domain.steps[1].state_observations[0]
    assert positive.objects[0].id == created["id"]
    assert positive.objects[0].fields == {"code": created["code"]}
    assert created["code"] == report.run_unique_values[projection]["record_code"]
    return domain, created, domain.steps[2].state_observations[0]


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_committed_deletion_passes_after_positive_existence_control(tmp_path, projections):
    with RecordsApp(tmp_path / "records file.sqlite") as app:
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        domain, _, facts = assert_lifecycle_reads(report, app, probe, projections[0])
        assert [step.status for step in domain.steps] == ["PASSED"] * 3
        assert facts.objects == []
        assert app.connection.in_transaction is False
        assert app.connection.execute("SELECT record_id FROM entries").fetchall() == []


class SuccessfulNoOpDelete(RecordsApp):
    def _delete_record(self, record_id):
        pass


class UncommittedDelete(RecordsApp):
    def _delete_record(self, record_id):
        self.connection.execute("DELETE FROM entries WHERE record_id = ?", (record_id,))


class WrongTargetDelete(RecordsApp):
    def _delete_record(self, record_id):
        # The fixture seeds a different committed record before the Scenario.
        self.connection.execute("DELETE FROM entries WHERE record_id = ?", (record_id - 1,))
        self.connection.commit()


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("app_type", [SuccessfulNoOpDelete, UncommittedDelete, WrongTargetDelete])
def test_successful_delete_response_cannot_hide_surviving_committed_record(tmp_path, projections, app_type):
    with app_type(tmp_path / "surviving.sqlite") as app:
        if app_type is WrongTargetDelete:
            app.connection.execute("INSERT INTO entries (business_code, label) VALUES (?, ?)",
                                   ("other-code", "Other record"))
            app.connection.commit()
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        domain, created, facts = assert_lifecycle_reads(report, app, probe, projections[0])
        assert report.status == "FAILED"
        assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "FAILED"]
        assert len(facts.objects) == 1
        assert facts.objects[0].id == created["id"] and facts.objects[0].fields == {}
        failed = [check for check in domain.checks if not check.ok]
        assert [(check.point, check.check, check.step) for check in failed] == [
            ("backend_state", "object_absent", "delete")]
        if app_type is UncommittedDelete:
            assert app.connection.in_transaction is True
            assert app.connection.execute("SELECT record_id FROM entries").fetchall() == []
        else:
            assert app.connection.in_transaction is False
            assert app.connection.execute("SELECT record_id FROM entries").fetchall() == [(created["id"],)]


class AlwaysEmptyProbe(AuditedProbe):
    def observe_object(self, query):
        return replace(super().observe_object(query), objects=[])


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_positive_existence_control_catches_an_always_empty_probe(tmp_path, projections):
    with RecordsApp(tmp_path / "exists.sqlite") as app:
        probe = AlwaysEmptyProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED"]
        assert len(app.requests) == 2 and len(probe.queries) == 1
        assert app.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (1,)
        assert not any(check.check == "object_absent" for check in report.domains[0].checks)


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_positive_existence_control_catches_an_empty_wrong_database(tmp_path, projections):
    with RecordsApp(tmp_path / "writer.sqlite") as app, RecordsApp(tmp_path / "other.sqlite") as other:
        probe = SQLiteRecordProbe(other.database)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED"]
        assert len(app.requests) == 2 and len(probe.queries) == 1
        assert app.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (1,)
        assert other.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (0,)


class FaultAfterDeleteProbe(AuditedProbe):
    def __init__(self, app, fault):
        super().__init__(app)
        self.fault = fault

    def _connect(self):
        connection = super()._connect()
        if self.fault == "query-failure" and len(self.app.requests) == 3:
            connection.set_authorizer(lambda *args: sqlite3.SQLITE_DENY)
        return connection

    def observe_object(self, query):
        facts = super().observe_object(query)
        return replace(facts, complete=False) if self.fault == "incomplete" and query.fields == () else facts


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["query-failure", "incomplete"])
def test_failed_or_incomplete_absence_acquisition_is_error(tmp_path, projections, fault):
    with RecordsApp(tmp_path / "unavailable.sqlite") as app:
        probe = FaultAfterDeleteProbe(app, fault)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        domain = report.domains[0]
        assert [record.status for record in domain.provider_recordings] == [201, 200, 204]
        assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "ERROR"]
        assert report.status != "PASSED"
        assert len(app.requests) == 3 and len(probe.queries) == 2
        assert app.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (0,)
        assert not any(check.check == "object_absent" and check.ok for check in domain.checks)
        if fault == "query-failure":
            assert domain.steps[-1].state_observations == []
        for visible in (repr(report), repr(domain), domain.steps[-1].detail):
            assert str(app.database) not in visible and "not authorized" not in visible


def test_empty_field_selection_still_looks_up_actual_rows_read_only(tmp_path):
    from refracto import ports

    with RecordsApp(tmp_path / "readonly.sqlite") as app:
        app.connection.execute("INSERT INTO entries (business_code, label) VALUES (?, ?)",
                               ("actual-code", "Actual name"))
        app.connection.commit()
        probe = SQLiteRecordProbe(app.database)
        query = ports.ObjectStateQuery(observation_id="observation", projection="backend", step_id="delete",
            trace_id="trace", user="creator", session_generation=1, object="record", id=1, fields=())
        facts = probe.observe_object(query)
        assert len(facts.objects) == 1 and facts.objects[0].id == 1 and facts.objects[0].fields == {}
        assert probe.observe_object(replace(query, id=2)).objects == []
        with closing(probe._connect()) as connection:
            connection.execute("PRAGMA query_only = OFF")
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("DELETE FROM entries")
        assert app.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (1,)


def test_contract_records_absence_as_outside_scope_without_querying_again(tmp_path):
    with RecordsApp(tmp_path / "contract.sqlite") as app:
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=("backend", "contract"))
        assert report.status == "PASSED", report.localize()
        assert len(app.requests) == 3 and len(probe.queries) == 2
        contract = report.domains[1]
        assert not any(step.state_observations for step in contract.steps)
        assert contract.not_checked == ["verify_exists: object_field_equals is outside contract scope",
                                        "delete: object_absent is outside contract scope"]


def test_example_runner_runs_complete_lifecycle(capsys):
    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["PASSED", "create PASSED", "verify_exists PASSED", "delete PASSED"]


def test_approved_lifecycle_example_preserves_actions_assertions_and_bindings():
    source = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    assert source["schema_version"] == 1 and source["users"] == ["creator"]
    assert source["parameters"] == {"record_code": {"from_run": "unique"}, "record_name": "Example record"}
    assert [step["id"] for step in source["steps"]] == ["create", "verify_exists", "delete"]
    create, read, delete = source["steps"]
    assert create["on_failure"] == read["on_failure"] == "stop"
    assert create["do"] == {"request": {"method": "POST", "path": ["records"], "body": {
        "code": {"from_parameter": "record_code"}, "name": {"from_parameter": "record_name"}}}}
    assert create["expect"]["response"] == [
        {"check": "status_equals", "value": 201}, {"check": "success"}, {"check": "has", "field": "id"}]
    reference = {"from_step": "create", "response_field": "id"}
    assert read["do"] == {"request": {"method": "GET", "path": ["records", reference]}}
    assert read["expect"]["response"] == [{"check": "status_equals", "value": 200},
        {"check": "field_equals", "field": "id", "value": reference}]
    assert read["expect"]["backend_state"] == [{"check": "object_field_equals", "object": "record",
        "id": reference, "field": "code", "value": {"from_parameter": "record_code"}}]
    assert delete["do"] == {"request": {"method": "DELETE", "path": ["records", reference]}}
    assert delete["expect"] == {"response": [{"check": "status_equals", "value": 204}],
        "backend_state": [{"check": "object_absent", "object": "record", "id": reference}]}
    assert [step.id for step in load_scenario(SCENARIO).steps] == ["create", "verify_exists", "delete"]
