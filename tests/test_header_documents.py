"""Business-header execution on an independent, enveloped document service."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from adapters.documents.api import DocumentApiDriver
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.runner import run_scenario


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/documents/scenarios/idempotent_create.yaml"
PROJECTIONS = [("backend", "contract"), ("e2e",)]


def write_example(tmp_path, change):
    declaration = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(declaration)
    path = tmp_path / "headers.yaml"
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_documents_retry_headers_and_actual_invocation_are_observed(projections):
    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(EXAMPLE, adapters, projections=projections)

    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert app.request_count == 3  # Contract only consumes the protected recordings.
    records = report.domains[0].provider_recordings
    assert [record.status for record in records] == [201, 200, 200]
    assert records[0].json == records[1].json
    assert app.requests[0][2] == app.requests[1][2] == {"title": "retry-notes", "category": "memo"}
    for record, (_, _, _, observed) in zip(records, app.requests, strict=True):
        assert record.request_header_items == list(observed.items())
        assert "x-session-key" in observed
    assert records[0].request.headers == {"Idempotency-Key": "document-create-example-001"}
    assert records[1].request.headers == {"idempotency-key": "document-create-example-001"}
    assert records[2].request.headers == {}
    assert dict(records[0].header_items)["cache-control"] == "no-store"
    assert len(adapters.normalizer.normalize(records[-1]).fields["documents"]) == 1


class DuplicateCreationWithOldIdentifier(DocumentRestApp):
    """Create a duplicate but disguise the retry response with the first body."""

    def __init__(self):
        super().__init__()
        self.first_body = None

    def handle(self, method, path, body=None, headers=None):
        is_create = method == "POST" and path == "/v3/documents"
        if is_create and self.first_body is not None:
            self._idempotency.clear()
        response = super().handle(method, path, body, headers)
        if is_create:
            if self.first_body is None:
                self.first_body = deepcopy(response.body)
            else:
                return RestResponse(200, deepcopy(self.first_body), response.headers)
        return response


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_final_document_read_detects_duplicate_even_when_retry_echoes_first_id(projections):
    app = DuplicateCreationWithOldIdentifier()
    report = run_scenario(EXAMPLE, build_adapters(app), projections=projections)

    assert report.status == "FAILED"
    assert {domain.status for domain in report.domains} == {"FAILED"}
    assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "FAILED"]
    assert app.request_count == 3
    records = report.domains[0].provider_recordings
    assert records[0].json == records[1].json
    nodes = records[-1].json["result_set"]["nodes"]
    assert len(nodes) == 2 and nodes[0]["identifier"] != nodes[1]["identifier"]
    failures = [check for check in report.domains[0].checks if not check.ok]
    assert len(failures) == 1 and failures[0].check == "collection_matching_count"


def test_document_service_retry_is_scoped_to_principal_key_and_exact_body():
    app = DocumentRestApp()
    _, owner_token = app.authenticate("editor")
    _, peer_token = app.authenticate("reader")
    body = {"title": "same-title", "category": "memo"}
    owner_headers = {"X-Session-Key": owner_token, "Idempotency-Key": "stable-key"}
    first = app.handle("POST", "/v3/documents", body, owner_headers)
    replay = app.handle("POST", "/v3/documents", dict(body), owner_headers)
    conflict = app.handle("POST", "/v3/documents", {**body, "category": "guide"}, owner_headers)
    peer = app.handle("POST", "/v3/documents", body,
                      {"x-session-key": peer_token, "idempotency-key": "stable-key"})
    _, renewed_token = app.authenticate("editor")
    renewed = app.handle("POST", "/v3/documents", body,
                         {"x-session-key": renewed_token, "idempotency-key": "stable-key"})
    unkeyed = [app.handle("POST", "/v3/documents", body, {"x-session-key": owner_token})
               for _ in range(2)]

    assert [first.status, replay.status, conflict.status, peer.status, renewed.status] == [201, 200, 409, 201, 200]
    assert first.body == replay.body == renewed.body
    assert first.body != peer.body
    assert conflict.body["fault"]["code"] == "idempotency_conflict"
    assert [response.status for response in unkeyed] == [201, 201]
    assert unkeyed[0].body != unkeyed[1].body  # No title uniqueness rule.
    assert first.headers["cache-control"] == replay.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("name", ["x-session-key", "X-SeSsIoN-KeY"])
def test_document_credential_collision_is_rejected_before_target_invocation(name):
    app = DocumentRestApp()
    driver = DocumentApiDriver(app)
    with pytest.raises(ValueError, match="credential") as error:
        driver.send(ports.RequestSpec("GET", "/v3/documents", headers={name: "business-secret"}),
                    {"session_key": "credential-secret"})
    assert app.requests == [] and driver.sent == []
    assert "business-secret" not in str(error.value)
    assert "credential-secret" not in str(error.value)


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("headers", [{}, {"IDEMPOTENCY-KEY": "different-key"}])
def test_wrong_actual_document_headers_fail_but_preserve_response_and_continuation(projections, headers):
    class ChangedInvocation(DocumentApiDriver):
        def send(self, spec, session):
            sent = replace(spec, headers=headers if spec.headers else {})
            response = super().send(sent, session)
            response.request = spec
            return response

    app = DocumentRestApp()
    adapters = build_adapters(app)
    adapters.api = ChangedInvocation(app)
    report = run_scenario(EXAMPLE, adapters, projections=projections)

    assert report.domains[0].steps[0].status == "FAILED", report.localize()
    assert report.domains[0].steps[1].status == "FAILED"
    assert app.request_count == 3
    records = report.domains[0].provider_recordings
    assert records[0].status == 201
    assert records[0].json["resource"]["document"]["identifier"]
    assert dict(records[0].request_header_items).get("idempotency-key") == headers.get("IDEMPOTENCY-KEY")
    assert report.domains[0].steps[-1].after_failures


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_document_empty_business_header_is_sent_without_credential_leak(tmp_path, projections):
    secret = "header-sentinel-sensitive-value"

    def change(declaration):
        declaration["steps"][0]["do"]["request"]["headers"].update({"X-Empty": "", "X-Note": secret})

    app = DocumentRestApp()
    report = run_scenario(write_example(tmp_path, change), build_adapters(app), projections=projections)
    assert report.status == "PASSED", report.localize()
    observed = app.requests[0][3]
    assert observed["x-empty"] == "" and observed["x-note"] == secret
    record = report.domains[0].provider_recordings[0]
    for value in (secret, observed["x-session-key"]):
        assert value not in repr(record)
        assert value not in repr(record.request)
        assert value not in repr(report)
        assert value not in repr(report.localize())


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("check,items,expected", [
    ("header_absent", None, "ERROR"),
    ("header_absent", [], "PASSED"),
    ("header_absent", [("X-Public", "")], "FAILED"),
    ("header_absent", [("X-Public", "a"), ("x-public", "b")], "ERROR"),
    ("header_equals", None, "ERROR"),
    ("header_equals", [], "FAILED"),
    ("header_equals", [("x-public", "exact")], "PASSED"),
    ("header_equals", [("x-public", "Exact")], "FAILED"),
    ("header_equals", [("X-Public", "exact"), ("x-public", "exact")], "ERROR"),
    ("header_equals", [("X-Public", "exact"), ("Set-Cookie", "a"), ("set-cookie", "b")], "PASSED"),
    ("header_equals", [("x-public", None)], "ERROR"),
])
def test_document_response_checks_require_complete_single_value_evidence(tmp_path, projections, check, items, expected):
    def change(declaration):
        declaration["steps"] = declaration["steps"][:1]
        assertion = {"check": check, "header": "X-Public"}
        if check == "header_equals":
            assertion["value"] = "exact"
        declaration["steps"][0]["expect"]["response"] = [assertion]

    class EvidenceVariant(DocumentApiDriver):
        def send(self, spec, session):
            response = super().send(spec, session)
            response.header_items = deepcopy(items)
            response.headers = {"X-Public": "exact"}  # Legacy mapping cannot repair raw evidence.
            return response

    app = DocumentRestApp()
    adapters = build_adapters(app)
    adapters.api = EvidenceVariant(app)
    report = run_scenario(write_example(tmp_path, change), adapters, projections=projections)
    assert report.status == ("PASSED" if expected == "PASSED" else "FAILED"), report.localize()
    assert {step.status for domain in report.domains for step in domain.steps} == {expected}
    assert app.request_count == 1
