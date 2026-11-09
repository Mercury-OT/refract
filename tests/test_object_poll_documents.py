"""A second domain checks a deferred update with string IDs and one snapshot."""

from copy import deepcopy
from dataclasses import replace

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.runner import PollConfig, run_scenario


class DeferredDocuments(DocumentRestApp):
    def __init__(self):
        super().__init__()
        self.pending = None

    def handle(self, method, path, body=None, headers=None):
        before = deepcopy(self._documents)
        response = super().handle(method, path, body, headers)
        if method == "PATCH" and response.status == 200:
            identity = path.rsplit("/", 1)[-1]
            self.pending = (identity, deepcopy(self._documents[identity]))
            self._documents = before
            return RestResponse(202, None)
        return response

    def complete_job(self, mode, tick):
        if self.pending is None or mode == "no-job":
            return
        identity, document = self.pending
        if mode == "matched":
            self._documents[identity] = deepcopy(document)
        else:
            # Each condition becomes true, but never in the same snapshot.
            self._documents[identity]["content"] = {
                "phase": "archived" if tick % 2 else "queued", "ready": tick % 2 == 0}


class DocumentProbe(ports.ObjectStateProbe):
    def __init__(self, app, fault=None):
        self.app = app
        self.fault = fault
        self.queries = []
        self.request_counts = []

    def observe_object(self, query):
        if query.object != "document" or type(query.id) is not str:
            raise ValueError("unsupported object")
        if not set(query.fields) <= {"title", "phase", "ready"}:
            raise ValueError("unsupported fields")
        self.queries.append(query)
        self.request_counts.append(self.app.request_count)
        document = deepcopy(self.app._documents.get(query.id))
        fields = {} if document is None else {
            "title": document["properties"]["title"],
            "phase": document["content"]["phase"], "ready": document["content"]["ready"]}
        facts = ports.ObjectStateFacts(query=query, source="synthetic-documents", complete=True,
            objects=[] if document is None else [ports.ObservedObject(id=document["identifier"],
                fields={key: fields[key] for key in query.fields})])
        if self.fault == "incomplete" and "phase" in query.fields:
            return replace(facts, complete=False)
        return facts


class JobClock:
    def __init__(self, app, mode):
        self.app, self.mode = app, mode
        self.elapsed, self.ticks = 0.0, 0

    def now(self):
        return self.elapsed

    def sleep(self, duration):
        self.ticks += 1
        self.app.complete_job(self.mode, self.ticks)
        self.elapsed += duration


def scenario(tmp_path):
    identity = {"from_step": "create", "response_field": "document_id"}
    path = tmp_path / "document-poll.yaml"
    content = {"schema_version": 1, "scenario": "documents.deferred_update", "users": ["editor"],
        "parameters": {"title": {"from_run": "unique"}}, "steps": [
        {"id": "create", "on_failure": "stop", "do": {"request": {"method": "POST", "path": ["documents"],
            "body": {"title": {"from_parameter": "title"}, "category": "reference",
                     "content": {"phase": "queued", "ready": False}}}},
         "expect": {"response": [{"check": "status_equals", "value": 201},
             {"check": "has", "field": "document_id"}]}},
        {"id": "verify_exists", "on_failure": "stop", "do": {"request": {"method": "GET",
            "path": ["documents", deepcopy(identity)]}}, "expect": {
            "response": [{"check": "status_equals", "value": 200}],
            "backend_state": [{"check": "object_field_equals", "object": "document", "id": deepcopy(identity),
                "field": "title", "value": {"from_parameter": "title"}}]}},
        {"id": "archive", "do": {"request": {"method": "PATCH", "path": ["documents", deepcopy(identity)],
            "body": {"content": {"phase": "archived", "ready": True}}}},
         "object_poll": {"on_timeout": "FAIL"}, "expect": {
            "response": [{"check": "status_equals", "value": 202}],
            "backend_state": [{"check": "object_field_equals", "object": "document", "id": deepcopy(identity),
                "field": "phase", "value": "archived"},
                {"check": "object_field_equals", "object": "document", "id": deepcopy(identity),
                 "field": "ready", "value": True}]}}
        ]}
    path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("projection", ["backend", "e2e"])
@pytest.mark.parametrize("mode", ["matched", "alternating", "no-job"])
def test_deferred_document_fields_must_match_together_without_replaying_patch(tmp_path, projection, mode):
    app = DeferredDocuments()
    probe = DocumentProbe(app)
    adapters = build_adapters(app)
    adapters.object_state = probe
    clock = JobClock(app, mode)
    report = run_scenario(scenario(tmp_path), adapters, projections=(projection,),
                         poll_config=PollConfig(timeout=0.3, interval=0.1), now=clock.now, sleep=clock.sleep)
    domain = report.domains[0]
    step = domain.steps[-1]
    expected = "PASSED" if mode == "matched" else "FAILED"
    assert report.status == expected and step.status == expected
    assert [step.status for step in domain.steps[:2]] == ["PASSED", "PASSED"]
    assert app.request_count == 3 and step.attempts == 1
    assert [method for method, _, _, _ in app.requests] == ["POST", "GET", "PATCH"]
    assert [record.status for record in domain.provider_recordings] == [201, 200, 202]
    assert step.object_poll.outcome == ("matched" if mode == "matched" else "timeout")
    assert step.object_poll.attempts == (2 if mode == "matched" else 3)
    assert probe.request_counts == [2] + [3] * step.object_poll.attempts
    assert [query.fields for query in probe.queries] == [("title",)] + [("phase", "ready")] * step.object_poll.attempts
    identity = domain.provider_recordings[0].json["resource"]["document"]["identifier"]
    assert type(identity) is str
    assert len({query.observation_id for query in probe.queries}) == len(probe.queries)
    assert all(query.id == identity and query.user == "editor" and query.projection == projection
               and query.session_generation == 1 for query in probe.queries)
    if mode == "alternating":
        observed = [facts.objects[0].fields for facts in step.state_observations]
        assert observed == [{"phase": "queued", "ready": False},
            {"phase": "archived", "ready": False}, {"phase": "queued", "ready": True}]
        assert not any(fields == {"phase": "archived", "ready": True} for fields in observed)
        assert not all(check.ok for check in step.checks)


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_incomplete_document_state_is_error_without_finishing_job(tmp_path, projection):
    app = DeferredDocuments()
    probe = DocumentProbe(app, "incomplete")
    adapters = build_adapters(app)
    adapters.object_state = probe
    clock = JobClock(app, "matched")
    report = run_scenario(scenario(tmp_path), adapters, projections=(projection,),
                         poll_config=PollConfig(timeout=0.3, interval=0.1), now=clock.now, sleep=clock.sleep)
    step = report.domains[0].steps[-1]
    assert report.status == "FAILED" and step.status == "ERROR"
    assert step.object_poll.outcome == "error" and step.object_poll.attempts == 1
    assert clock.ticks == 0 and app.request_count == 3 and len(probe.queries) == 2
    assert app.pending is not None
