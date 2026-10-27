"""Independent stateful consumers for complete response-field comparisons."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from adapters.documents.normalizer import DocumentResponseNormalizer
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "examples/minimal/rejected_update_preserves_content.yaml"
DOCUMENTS = ROOT / "examples/documents/scenarios/rejected_update_preserves_content.yaml"
PROJECTIONS = [("backend", "contract"), ("e2e",)]


class RecordsTarget:
    """Fixed service behavior; no declaration or expectation enters this target."""

    def __init__(self, fault=None):
        self.fault = fault
        self.records = {}
        self.owners = {}
        self.sessions = {}
        self.requests = []
        self.authentications = []
        self.reads = 0

    def identify(self, user):
        if user not in {"creator", "peer"}:
            raise ValueError("unknown account")
        return "records-account-" + user

    def login(self, user):
        principal = self.identify(user)
        token = str(uuid4())
        self.sessions[token] = principal
        self.authentications.append((principal, token))
        return ports.UserSession(principal_id=principal, authentication_id=token,
                                 credentials={"token": token})

    def handle(self, method, path, body, token):
        self.requests.append((method, path, deepcopy(body), token))
        principal = self.sessions.get(token)
        if method == "PATCH" and self.fault == "invalid_peer":
            principal = None
        if principal is None:
            return 401, {"error_code": "session_required"}
        if method == "POST" and path == "records":
            if not isinstance(body, dict) or not isinstance(body.get("content"), (dict, list)):
                return 400, {"error_code": "content_invalid"}
            record_id = str(uuid4())
            record = {"id": record_id, "content": deepcopy(body["content"])}
            self.records[record_id], self.owners[record_id] = record, principal
            return 201, deepcopy(record)
        parts = path.split("/")
        if len(parts) != 2 or parts[0] != "records" or parts[1] not in self.records:
            return 404, {"error_code": "record_missing"}
        record = self.records[parts[1]]
        if self.owners[parts[1]] != principal:
            if method == "PATCH" and self.fault == "mutate_on_denial":
                record["content"] = deepcopy(body["content"])
            code = "validation_failed" if self.fault == "wrong_reason" else "owner_required"
            return 403, {} if self.fault == "missing_reason" else {"error_code": code}
        if method == "PATCH":
            if not isinstance(body, dict) or set(body) != {"content"}:
                return 400, {"error_code": "content_invalid"}
            record["content"] = deepcopy(body["content"])
            return 200, deepcopy(record)
        if method == "GET":
            self.reads += 1
            result = deepcopy(record)
            if self.fault == "equal_errors":
                return 500, result
            if self.reads == 2 and self.fault == "wrong_id":
                result["id"] = "another-record"
            if self.fault == "missing_before" or (self.reads == 2 and self.fault == "missing_content"):
                del result["content"]
            return 200, result
        return 405, {"error_code": "method_not_allowed"}


class RecordsAuth:
    def __init__(self, target):
        self.target = target

    def identify(self, user):
        return self.target.identify(user)

    def session(self, user):
        return self.target.login(user)


class RecordsApi:
    def __init__(self, target):
        self.target = target

    def send(self, request, session):
        status, body = self.target.handle(request.method, request.path, request.body, session["token"])
        return ports.RecordedResponse(status, {}, body, json.dumps(body), None, request)


class RecordsNormalizer:
    def normalize(self, response):
        return ports.NormalizedResponse(200 <= response.status < 300,
            deepcopy(response.json), response.status, response)


class DocumentsFaults(DocumentRestApp):
    """Faults alter genuine service responses/state, not expected assertions."""

    def __init__(self, fault=None):
        super().__init__()
        self.fault, self.reads = fault, 0

    def handle(self, method, path, body=None, headers=None):
        if method == "PATCH" and self.fault == "invalid_peer":
            self._sessions.pop(headers["x-session-key"], None)
        response = super().handle(method, path, body, headers)
        if method == "PATCH" and response.status == 403:
            if self.fault == "mutate_on_denial":
                self._documents[path.split("/")[-1]]["content"] = deepcopy(body["content"])
            if self.fault == "wrong_reason":
                return self._rejection(403, "validation_failed", "input was rejected")
            if self.fault == "missing_reason":
                return RestResponse(403, {"receipt": {"state": "rejected"}}, response.headers)
        if method == "GET" and path.startswith("/v3/documents/") and response.status == 200:
            self.reads += 1
            data = deepcopy(response.body)
            document = data["resource"]["document"]
            if self.fault == "equal_errors":
                data["receipt"]["state"] = "rejected"
                return RestResponse(500, data, response.headers)
            if self.reads == 2 and self.fault == "wrong_id":
                document["identifier"] = "another-document"
            if self.fault == "missing_before" or (self.reads == 2 and self.fault == "missing_content"):
                del document["content"]
            return RestResponse(response.status, data, response.headers)
        return response


def consumer(kind, fault=None):
    if kind == "documents":
        target = DocumentsFaults(fault)
        return target, build_adapters(target), DOCUMENTS
    target = RecordsTarget(fault)
    adapters = Adapters(auth=RecordsAuth(target), api=RecordsApi(target), state=None, ui=None,
        recorder_factory=InMemoryRecorder, normalizer=RecordsNormalizer(),
        resolve_request=lambda template: ports.RequestSpec(
            template.method, template.path, deepcopy(template.body)))
    return target, adapters, RECORDS


def write_variant(tmp_path, source, change):
    declaration = yaml.safe_load(source.read_text())
    change(declaration)
    path = tmp_path / "comparison.yaml"
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


def stored_content(target):
    records = target._documents if isinstance(target, DocumentRestApp) else target.records
    assert len(records) == 1
    return deepcopy(next(iter(records.values()))["content"])


def content_checks(step):
    # The approved final step ends with exactly these two content obligations.
    checks = step.checks[-2:]
    assert [check.check for check in checks] == ["field_equals", "field_not_equals"]
    return {check.check: check.ok for check in checks}


def test_approved_records_yaml_is_exact_and_has_no_hidden_preparation():
    raw = yaml.safe_load(RECORDS.read_text())
    assert raw["schema_version"] == 1
    assert raw["scenario"] == "records.rejected_update_preserves_content"
    assert raw["users"] == ["creator", "peer"]
    assert raw["parameters"] == {
        "original_content": {"title": "Original record", "status": "draft", "tags": ["review", "shared"]},
        "attempted_content": {"title": "Unexpected change", "status": "published", "tags": ["edited"]}}
    create, before, attempt, after = raw["steps"]
    assert [step["id"] for step in raw["steps"]] == ["create", "read_before", "peer_attempts_update", "read_after"]
    assert [step["user"] for step in raw["steps"]] == ["creator", "creator", "peer", "creator"]
    assert [step.get("on_failure") for step in raw["steps"]] == ["stop", "stop", None, None]
    identity = {"from_step": "create", "response_field": "id"}
    assert create["do"] == {"request": {"method": "POST", "path": ["records"],
        "body": {"content": {"from_parameter": "original_content"}}}}
    assert before["do"] == after["do"] == {"request": {"method": "GET", "path": ["records", identity]}}
    assert attempt["do"] == {"request": {"method": "PATCH", "path": ["records", identity],
        "body": {"content": {"from_parameter": "attempted_content"}}}}
    assert create["expect"]["response"] == [
        {"check": "status_equals", "value": 201}, {"check": "success"}, {"check": "has", "field": "id"}]
    common = [{"check": "status_equals", "value": 200}, {"check": "success"},
              {"check": "field_equals", "field": "id", "value": identity}]
    assert before["expect"]["response"] == common + [
        {"check": "field_equals", "field": "content", "value": {"from_parameter": "original_content"}}]
    assert attempt["expect"]["response"] == [
        {"check": "status_equals", "value": 403}, {"check": "failure"},
        {"check": "field_equals", "field": "error_code", "value": "owner_required"}]
    assert after["expect"]["response"] == common + [
        {"check": "field_equals", "field": "content", "value": {"from_step": "read_before", "response_field": "content"}},
        {"check": "field_not_equals", "field": "content", "value": {"from_parameter": "attempted_content"}}]
    assert [step.id for step in load_scenario(RECORDS).steps] == [step["id"] for step in raw["steps"]]


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_complete_read_before_and_after_real_refusal(kind, projections):
    target, adapters, path = consumer(kind)
    raw = yaml.safe_load(path.read_text())
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert all(domain.status == "PASSED" for domain in report.domains)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED"] * 4
    assert [response.status for response in domain.provider_recordings] == [201, 200, 403, 200]
    assert len(target.requests) == 4  # Contract does not issue another read or write.
    assert len(target.authentications) == 2
    assert target.authentications[0][0] != target.authentications[1][0]
    assert target.requests[0][-1] == target.requests[1][-1] == target.requests[3][-1]
    assert target.requests[1][-1] != target.requests[2][-1]
    assert target.requests[1][1] == target.requests[2][1] == target.requests[3][1]
    assert stored_content(target) == raw["parameters"]["original_content"]
    assert content_checks(domain.steps[-1]) == {"field_equals": True, "field_not_equals": True}
    observed = adapters.normalizer.normalize(domain.provider_recordings[-1])
    assert observed.fields["content"] == stored_content(target)


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_actual_unauthorized_state_change_is_detected_despite_refusal(kind, projections):
    target, adapters, path = consumer(kind, "mutate_on_denial")
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "FAILED"
    assert all(domain.status == "FAILED" for domain in report.domains)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "PASSED", "FAILED"]
    assert domain.provider_recordings[2].status == 403
    assert stored_content(target) == yaml.safe_load(path.read_text())["parameters"]["attempted_content"]
    assert content_checks(domain.steps[-1]) == {"field_equals": False, "field_not_equals": False}
    assert len(target.requests) == 4


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["wrong_id", "missing_content", "wrong_reason", "missing_reason", "invalid_peer"])
def test_wrong_identity_missing_content_and_wrong_rejection_cannot_pass(kind, projections, fault):
    target, adapters, path = consumer(kind, fault)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "FAILED", report.localize()
    assert all(domain.status == "FAILED" for domain in report.domains)
    domain = report.domains[0]
    assert len(target.requests) == 4
    if fault == "missing_content":
        assert content_checks(domain.steps[-1]) == {"field_equals": False, "field_not_equals": False}
    elif fault == "wrong_id":
        assert domain.steps[-1].status == "FAILED"
        assert content_checks(domain.steps[-1]) == {"field_equals": True, "field_not_equals": True}
    else:
        assert domain.steps[2].status == "FAILED" and domain.steps[3].status == "PASSED"
        assert domain.steps[3].after_failures == ["peer_attempts_update"]
        assert domain.provider_recordings[2].status == (401 if fault == "invalid_peer" else 403)


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["equal_errors", "missing_before"])
def test_no_successful_baseline_stops_the_approved_workflow(kind, projections, fault):
    target, adapters, path = consumer(kind, fault)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED", "BLOCKED"]
    assert len(target.requests) == 2


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_equal_error_contents_are_not_successful_business_evidence(tmp_path, kind, projections):
    target, adapters, source = consumer(kind, "equal_errors")
    path = write_variant(tmp_path, source, lambda raw: raw["steps"][1].pop("on_failure"))
    report = run_scenario(path, adapters, projections=projections)
    domain = report.domains[0]
    assert report.status == "FAILED" and len(target.requests) == 4
    assert [step.status for step in domain.steps] == ["PASSED", "FAILED", "PASSED", "FAILED"]
    assert domain.provider_recordings[1].status == domain.provider_recordings[3].status == 500
    assert domain.provider_recordings[1].json == domain.provider_recordings[3].json
    assert content_checks(domain.steps[-1]) == {"field_equals": True, "field_not_equals": True}
    assert all(not check.ok for check in domain.steps[-1].checks if check.check in {"success", "status_equals"})


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_removing_comparisons_demonstrates_actual_missing_obligation(tmp_path, kind, projections):
    target, adapters, source = consumer(kind, "mutate_on_denial")
    original = source.read_bytes()
    path = write_variant(tmp_path, source,
        lambda raw: raw["steps"][-1]["expect"].update(response=raw["steps"][-1]["expect"]["response"][:3]))
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED"
    assert stored_content(target) == yaml.safe_load(source.read_text())["parameters"]["attempted_content"]
    assert source.read_bytes() == original


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_legitimate_content_change_requires_different_before_and_equal_intended(tmp_path, kind, projections):
    def change(raw):
        update = raw["steps"][2]
        update["user"] = "creator"
        update["expect"]["response"] = [{"check": "status_equals", "value": 200}, {"check": "success"}]
        raw["steps"][-1]["expect"]["response"][-2]["check"] = "field_not_equals"
        raw["steps"][-1]["expect"]["response"][-1]["check"] = "field_equals"
    target, adapters, source = consumer(kind)
    path = write_variant(tmp_path, source, change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert stored_content(target) == yaml.safe_load(path.read_text())["parameters"]["attempted_content"]
    assert len(target.authentications) == 1 and len(target.requests) == 4


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", [None, "mutate_on_denial"])
def test_complete_list_field_uses_real_target_content(tmp_path, kind, projections, fault):
    def change(raw):
        raw["parameters"] = {"original_content": [{"label": "first", "flags": [False, 0]}, "second"],
                             "attempted_content": ["second", {"label": "first", "flags": [False, 0]}]}
    target, adapters, source = consumer(kind, fault)
    path = write_variant(tmp_path, source, change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == ("FAILED" if fault else "PASSED"), report.localize()
    assert type(stored_content(target)) is list


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_unchanged_inequality_target_cannot_pass(tmp_path, kind, projections):
    def change(raw):
        raw["parameters"]["attempted_content"] = deepcopy(raw["parameters"]["original_content"])
    target, adapters, source = consumer(kind)
    path = write_variant(tmp_path, source, change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "FAILED"
    assert all(domain.status == "FAILED" for domain in report.domains)
    assert content_checks(report.domains[0].steps[-1]) == {"field_equals": True, "field_not_equals": False}
    assert len(target.requests) == 4


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_unknown_account_blocks_before_preparation(tmp_path, kind, projections):
    def change(raw):
        raw["users"][1] = "unconfigured_account"
        raw["steps"][2]["user"] = "unconfigured_account"
    target, adapters, source = consumer(kind)
    path = write_variant(tmp_path, source, change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["ERROR", "BLOCKED", "BLOCKED", "BLOCKED"]
    assert target.requests == [] and target.authentications == []


def test_document_service_validates_content_and_returns_stable_complete_snapshots():
    app = DocumentRestApp()
    _, owner = app.authenticate("creator")
    _, peer = app.authenticate("peer")
    headers = {"x-session-key": owner}
    original = {"arbitrary": {"members": [False, 0, None]}, "extra": "retained"}
    body = {"title": "Complete content", "category": "memo", "content": deepcopy(original)}
    created = app.handle("POST", "/v3/documents", body, headers)
    path = "/v3/documents/" + created.body["resource"]["document"]["identifier"]
    before = app.handle("GET", path, headers=headers)
    body["content"]["extra"] = "changed outside target"
    assert stored_content(app) == original
    denied = app.handle("PATCH", path, {"content": []}, {"x-session-key": peer})
    assert denied.status == 403 and stored_content(app) == original
    for invalid in ({}, {"content": 1}, {"content": [], "extra": True}):
        assert app.handle("PATCH", path, invalid, headers).status == 400
        assert stored_content(app) == original
    updated = app.handle("PATCH", path, {"content": [{"revision": 2}]}, headers)
    assert updated.status == 200 and stored_content(app) == [{"revision": 2}]
    for response in (created, before):
        assert response.body["resource"]["document"]["content"] == original
    assert app.handle("POST", "/v3/documents", {"title": "Invalid", "category": "memo", "content": None}, headers).status == 400
    assert len(app._documents) == 1


@pytest.mark.parametrize("content", [{"arbitrary": {"nested": [None, False, 1, "x"]}}, [], {}, None, "invalid"])
def test_document_normalization_retains_complete_selected_content_including_malformed_values(content):
    raw = ports.RecordedResponse(200, {}, {"receipt": {"state": "accepted"}, "resource": {
        "document": {"identifier": "document-1", "properties": {"title": "Title", "category": "memo"},
                     "content": deepcopy(content)}}}, "", None, ports.RequestSpec("GET", "/v3/documents/document-1"))
    result = DocumentResponseNormalizer().normalize(raw)
    assert "content" in result.fields and type(result.fields["content"]) is type(content)
    assert result.fields["content"] == content
    assert result.raw is raw
