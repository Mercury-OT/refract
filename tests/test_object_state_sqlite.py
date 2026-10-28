"""Actual committed-state reads, separate from the synthetic API connection."""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest
import yaml

from adapters.sqlite_records.adapter import SQLiteRecordProbe, build_adapters
from examples.sqlite_records.app import RecordsApp
from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario


SCENARIO = (Path(__file__).resolve().parents[1] / "examples/sqlite_records/scenarios"
            / "create_and_verify_storage.yaml")
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
        self.connections.append(connection)
        connection.set_trace_callback(self.statements.append)
        return connection

    def observe_object(self, query):
        self.action_counts.append(len(self.app.requests))
        before = sha256(self.app.database.read_bytes()).hexdigest()
        facts = super().observe_object(query)
        self.hashes.append((before, sha256(self.app.database.read_bytes()).hexdigest()))
        return facts


def _assert_real_reads(report, app, probe, projection):
    domain = report.domains[0]
    assert domain.projection == projection
    assert [step.step_id for step in domain.steps] == ["create", "read"]
    assert len(app.requests) == 2
    assert [record.status for record in domain.provider_recordings] == [201, 200]
    created = domain.provider_recordings[0].json
    assert type(created["id"]) is int
    assert app.requests[1][1] == f"/records/{created['id']}"
    assert domain.provider_recordings[1].json["id"] == created["id"]
    assert all(check.ok for check in domain.checks if check.point == "response")
    assert len(probe.queries) == 1
    query = probe.queries[0]
    assert query.object == "record" and query.id == created["id"]
    assert query.fields == ("code", "name")
    assert query.step_id == "read" and query.projection == projection
    assert query.user == "creator" and query.session_generation == 1
    assert query.trace_id == domain.steps[1].trace_id
    assert probe.action_counts == [2]
    assert len(probe.connections) == 1 and probe.connections[0] is not app.connection
    assert len(probe.statements) == 1 and probe.statements[0].startswith("SELECT ")
    assert all(before == after for before, after in probe.hashes)
    assert len(domain.steps[1].state_observations) == 1
    facts = domain.steps[1].state_observations[0]
    assert facts.query == query and facts.source == "sqlite-records" and facts.complete is True
    return domain, created, facts


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_sqlite_committed_record_matches_observed_state(tmp_path, projections):
    with RecordsApp(tmp_path / "records file.sqlite") as app:
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        domain, created, facts = _assert_real_reads(report, app, probe, projections[0])
        assert [step.status for step in domain.steps] == ["PASSED", "PASSED"]
        assert len(facts.objects) == 1
        assert facts.objects[0].id == created["id"]
        assert facts.objects[0].fields == {"code": created["code"], "name": "Example record"}
        assert created["code"] == report.run_unique_values[projections[0]]["record_code"]
        assert app.connection.in_transaction is False


class UncommittedRecords(RecordsApp):
    def _commit_write(self):
        # A real transaction remains visible to this API's own GET connection.
        # The observer must not share that visibility or manufacture a record.
        pass


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_uncommitted_api_success_is_not_committed_state(tmp_path, projections):
    with UncommittedRecords(tmp_path / "uncommitted.sqlite") as app:
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        domain, created, facts = _assert_real_reads(report, app, probe, projections[0])
        assert app.connection.in_transaction is True
        assert app.connection.execute("SELECT record_id FROM entries").fetchall() == [(created["id"],)]
        assert facts.objects == []
        assert report.status == "FAILED"
        assert [step.status for step in domain.steps] == ["PASSED", "FAILED"]
        failed = [check for check in domain.checks if not check.ok]
        assert len(failed) == 2
        assert {(check.point, check.check, check.step) for check in failed} == {
            ("backend_state", "object_field_equals", "read")}


class WrongStoredName(RecordsApp):
    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if method == "POST" and response.status == 201:
            self.connection.execute("UPDATE entries SET label = ? WHERE record_id = ?",
                                    ("Changed stored name", response.body["id"]))
            self.connection.commit()
        return response


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_committed_wrong_name_fails_only_the_storage_name_obligation(tmp_path, projections):
    with WrongStoredName(tmp_path / "wrong-name.sqlite") as app:
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        domain, created, facts = _assert_real_reads(report, app, probe, projections[0])
        assert report.status == "FAILED" and domain.steps[1].status == "FAILED"
        assert facts.objects[0].fields == {"code": created["code"], "name": "Changed stored name"}
        state_checks = [check for check in domain.checks if check.point == "backend_state"]
        assert [check.ok for check in state_checks] == [True, False]
        assert app.connection.in_transaction is False


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_real_query_failure_is_error_not_an_absent_object(tmp_path, projections):
    # The probe can open this real database but its SELECT fails: no table exists.
    empty_database = tmp_path / "unconfigured.sqlite"
    sqlite3.connect(empty_database).close()
    with RecordsApp(tmp_path / "writer.sqlite") as app:
        probe = SQLiteRecordProbe(empty_database)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=projections)
        assert len(app.requests) == 2 and len(probe.queries) == 1
        domain = report.domains[0]
        assert [record.status for record in domain.provider_recordings] == [201, 200]
        assert domain.steps[1].status == "ERROR" and report.status != "PASSED"
        assert domain.steps[1].state_observations == []
        assert not any(check.point == "backend_state" and check.ok for check in domain.checks)
        for text in (repr(report), repr(domain), domain.steps[1].detail):
            assert str(empty_database) not in text and "no such table" not in text


def test_probe_connection_is_read_only_and_closed_after_snapshot(tmp_path):
    with RecordsApp(tmp_path / "readonly.sqlite") as app:
        probe = AuditedProbe(app)
        with closing(probe._connect()) as connection:
            assert connection.execute("PRAGMA query_only").fetchone() == (1,)
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("INSERT INTO entries (business_code, label) VALUES ('bad', 'bad')")
            connection.execute("PRAGMA query_only = OFF")
            # The URI's read-only mode still forbids writes even if query_only is disabled.
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("INSERT INTO entries (business_code, label) VALUES ('bad', 'bad')")
        assert app.connection.execute("SELECT COUNT(*) FROM entries").fetchone() == (0,)
        probe.connections.clear()
        probe.statements.clear()
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=("backend",))
        assert report.status == "PASSED"
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            probe.connections[0].execute("SELECT 1")


def test_contract_does_not_requery_or_claim_storage_observation(tmp_path):
    with RecordsApp(tmp_path / "contract.sqlite") as app:
        probe = AuditedProbe(app)
        report = run_scenario(SCENARIO, build_adapters(app, probe=probe), projections=("backend", "contract"))
        assert report.status == "PASSED", report.localize()
        assert len(app.requests) == 2 and len(probe.queries) == 1
        contract = report.domains[1]
        assert contract.projection == "contract"
        assert not any(step.state_observations for step in contract.steps)
        assert contract.not_checked == ["read: object_field_equals is outside contract scope"]


def test_only_actual_sqlite_values_are_returned_and_unknown_mappings_are_rejected(tmp_path):
    with RecordsApp(tmp_path / "mapping.sqlite") as app:
        probe = SQLiteRecordProbe(app.database)
        app.connection.execute("INSERT INTO entries (business_code, label) VALUES (?, ?)",
                               ("quote'code", "Literal stored name"))
        app.connection.commit()
        query = ports.ObjectStateQuery(observation_id="observation-1", projection="backend", step_id="read",
            trace_id="trace-1", user="creator", session_generation=1, object="record", id=1,
            fields=("code", "name"))
        facts = probe.observe_object(query)
        assert facts.objects[0].fields == {"code": "quote'code", "name": "Literal stored name"}
        for changed in (replace(query, object="unknown"), replace(query, fields=("unknown",)),
                        replace(query, id="1 OR 1=1")):
            with pytest.raises(ValueError, match="unsupported record observation"):
                probe.observe_object(changed)
        assert len(probe.queries) == 1


def test_approved_example_preserves_exact_actions_assertions_and_bindings():
    source = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    assert source["schema_version"] == 1 and source["users"] == ["creator"]
    assert source["parameters"] == {"record_code": {"from_run": "unique"}, "record_name": "Example record"}
    assert [step["id"] for step in source["steps"]] == ["create", "read"]
    create, read = source["steps"]
    assert create["on_failure"] == "stop"
    assert create["do"] == {"request": {"method": "POST", "path": ["records"],
        "body": {"code": {"from_parameter": "record_code"}, "name": {"from_parameter": "record_name"}}}}
    assert create["expect"]["response"] == [
        {"check": "status_equals", "value": 201}, {"check": "success"}, {"check": "has", "field": "id"}]
    reference = {"from_step": "create", "response_field": "id"}
    assert read["do"] == {"request": {"method": "GET", "path": ["records", reference]}}
    assert read["expect"]["response"] == [
        {"check": "status_equals", "value": 200}, {"check": "field_equals", "field": "id", "value": reference}]
    assert read["expect"]["backend_state"] == [
        {"check": "object_field_equals", "object": "record", "id": reference,
         "field": field, "value": {"from_parameter": parameter}}
        for field, parameter in (("code", "record_code"), ("name", "record_name"))]
    assert [step.id for step in load_scenario(SCENARIO).steps] == ["create", "read"]
