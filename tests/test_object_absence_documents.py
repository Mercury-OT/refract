"""A second, neutral string-ID domain using a test-only raw storage mapping."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp
from refracto import ports
from refracto.runner import run_scenario


def scenario(tmp_path):
    identity = {"from_step": "create", "response_field": "document_id"}
    path = tmp_path / "document-absence.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "scenario": "documents.absence",
        "users": ["editor"], "parameters": {"title": {"from_run": "unique"}}, "steps": [
            {"id": "create", "on_failure": "stop", "do": {"request": {
                "method": "POST", "path": ["documents"],
                "body": {"title": {"from_parameter": "title"}, "category": "reference"}}},
             "expect": {"response": [{"check": "status_equals", "value": 201},
                 {"check": "success"}, {"check": "has", "field": "document_id"}]}},
            {"id": "read", "on_failure": "stop", "do": {"request": {
                "method": "GET", "path": ["documents", deepcopy(identity)]}}, "expect": {
                    "response": [{"check": "status_equals", "value": 200},
                        {"check": "field_equals", "field": "document_id", "value": deepcopy(identity)}],
                    "backend_state": [{"check": "object_field_equals", "object": "document",
                        "id": deepcopy(identity), "field": "title", "value": {"from_parameter": "title"}}]}},
            {"id": "delete", "do": {"request": {"method": "DELETE", "path": ["documents", deepcopy(identity)]}},
             "expect": {"response": [{"check": "status_equals", "value": 204}],
                        "backend_state": [{"check": "object_absent", "object": "document", "id": deepcopy(identity)}]}}
        ]}, sort_keys=False), encoding="utf-8")
    return path


class StoredDocumentsProbe(ports.ObjectStateProbe):
    """Map the complete synthetic store, not its permission-filtered list API."""

    def __init__(self, app, fault=None):
        self.app = app
        self.fault = fault
        self.queries = []
        self.action_counts = []

    def observe_object(self, query):
        if query.object != "document" or type(query.id) is not str or not set(query.fields) <= {"title"}:
            raise ValueError("unsupported document observation")
        self.queries.append(query)
        self.action_counts.append(self.app.request_count)
        if self.fault == "query-failure" and query.fields == ():
            raise RuntimeError("synthetic acquisition failure")
        document = deepcopy(self.app._documents.get(query.id))
        objects = [] if document is None else [ports.ObservedObject(id=document["identifier"], fields={
            field: document["properties"][field] for field in query.fields})]
        facts = ports.ObjectStateFacts(query=query, source="synthetic-document-store", complete=True,
                                       objects=objects)
        if self.fault == "always-empty":
            return replace(facts, objects=[])
        if self.fault == "incomplete" and query.fields == ():
            return replace(facts, complete=False)
        return facts


class SurvivingDocumentDelete(DocumentRestApp):
    def __init__(self, *, soft_delete=False):
        super().__init__()
        self.soft_delete = soft_delete

    def handle(self, method, path, body=None, headers=None):
        # Preserve the target's validation, response shape and invocation count.
        # This test-only fault leaves the exact object after a successful DELETE.
        saved_documents, saved_owners = deepcopy(self._documents), deepcopy(self._owners)
        response = super().handle(method, path, body, headers)
        if method == "DELETE" and response.status == 204:
            document_id = path.rsplit("/", 1)[-1]
            self._documents[document_id] = saved_documents[document_id]
            self._owners[document_id] = saved_owners[document_id]
            if self.soft_delete:
                self._documents[document_id]["deleted"] = True
        return response


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("fault,expected", [(None, "PASSED"), ("surviving", "FAILED"),
    ("soft-delete", "FAILED"), ("incomplete", "ERROR"), ("query-failure", "ERROR")])
def test_document_string_id_absence_uses_actual_complete_store(tmp_path, projection, fault, expected):
    app = (SurvivingDocumentDelete(soft_delete=fault == "soft-delete")
           if fault in {"surviving", "soft-delete"} else DocumentRestApp())
    probe = StoredDocumentsProbe(app, fault)
    adapters = build_adapters(app)
    adapters.object_state = probe
    report = run_scenario(scenario(tmp_path), adapters, projections=(projection,))
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED", expected]
    assert (report.status == "PASSED") is (expected == "PASSED")
    assert app.request_count == 3 and probe.action_counts == [2, 3]
    assert [query.fields for query in probe.queries] == [("title",), ()]
    created_id = domain.provider_recordings[0].json["resource"]["document"]["identifier"]
    assert type(created_id) is str
    assert all(query.object == "document" and query.id == created_id and type(query.id) is str
               for query in probe.queries)
    assert app.requests[-1][:2] == ("DELETE", f"/v3/documents/{created_id}")
    assert all(check.ok for check in domain.checks if check.point == "response")
    assert (created_id in app._documents) is (fault in {"surviving", "soft-delete"})
    if expected in {"PASSED", "FAILED"}:
        facts = domain.steps[-1].state_observations[0]
        assert facts.source == "synthetic-document-store" and facts.complete is True
        if expected == "PASSED":
            assert facts.objects == []
        else:
            assert len(facts.objects) == 1
            assert facts.objects[0].id == created_id and facts.objects[0].fields == {}
    else:
        assert not any(check.check == "object_absent" and check.ok for check in domain.checks)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_document_positive_control_catches_empty_probe_before_delete(tmp_path, projection):
    app = DocumentRestApp()
    probe = StoredDocumentsProbe(app, "always-empty")
    adapters = build_adapters(app)
    adapters.object_state = probe
    report = run_scenario(scenario(tmp_path), adapters, projections=(projection,))
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED"]
    assert app.request_count == 2 and len(probe.queries) == 1
    assert len(app._documents) == 1
