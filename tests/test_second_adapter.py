import inspect
from copy import deepcopy
from pathlib import Path

import pytest

from refracto import ports, runner
from refracto.report import FAILED, PASSED

from adapters.documents import api, auth, normalizer
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_ROOT = ROOT / "examples" / "documents"
HAPPY_SCENARIO = DOCUMENTS_ROOT / "scenarios" / "create_list_delete.yaml"
REJECTION_SCENARIO = DOCUMENTS_ROOT / "scenarios" / "rejected_create.yaml"


class AcceptedRejectionApp(DocumentRestApp):
    """A deliberate mutant that turns a declared rejection into acceptance."""

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if response.status != 422:
            return response
        mutated = dict(response.body)
        mutated["receipt"] = {"state": "accepted", "operation": "create"}
        return RestResponse(200, mutated, response.headers)


class ChangedTargetTitleApp(DocumentRestApp):
    """A list-response mutant: one target changes, the unrelated member does not."""

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if not isinstance(response.body, dict) or "result_set" not in response.body:
            return response
        mutated = deepcopy(response.body)
        for node in mutated["result_set"]["nodes"]:
            if node["properties"]["title"] == "field-notes":
                node["properties"]["title"] = "changed-target-title"
        return RestResponse(response.status, mutated, response.headers)


def test_second_adapter_runs_server_id_filter_page_and_204_through_backend_contract():
    app = DocumentRestApp()
    adapters = build_adapters(app)

    rep = runner.run_scenario(
        HAPPY_SCENARIO,
        adapters,
        projections=("backend", "contract"),
    )

    assert rep.status == PASSED
    assert rep.degradations() == []
    assert len(adapters.api.sent) == 5
    assert adapters.api.sent[0].body == {"title": "other-notes", "category": "guide"}
    assert adapters.api.sent[1].body == {"title": "field-notes", "category": "guide"}
    assert adapters.api.sent[2].path == "/v3/documents"
    assert adapters.api.sent[2].query == {"category": "guide", "cursor": "0", "limit": "2"}
    assert app.requests[2][1] == "/v3/documents?category=guide&cursor=0&limit=2"
    created_id = adapters.api.sent[3].path.rsplit("/", 1)[-1]
    assert created_id.startswith("document-")
    assert created_id not in adapters.api.sent[1].body.values()
    assert app.request_count == 5
    listed = rep.domains[0].provider_recordings[2]
    documents = adapters.normalizer.normalize(listed).fields["documents"]
    assert [document["title"] for document in documents] == ["other-notes", "field-notes"]
    assert documents[1]["document_id"] == created_id
    assert documents[0]["document_id"] != created_id


def test_collection_assertion_kills_changed_target_after_unrelated_member():
    app = ChangedTargetTitleApp()
    adapters = build_adapters(app)
    rep = runner.run_scenario(HAPPY_SCENARIO, adapters, projections=("backend", "contract"))

    assert rep.status == FAILED
    assert {domain.projection: domain.status for domain in rep.domains} == {
        "backend": FAILED,
        "contract": FAILED,
    }
    assert app.request_count == 5  # Declared deletes run after assertion failure.
    listed = rep.domains[0].provider_recordings[2]
    documents = adapters.normalizer.normalize(listed).fields["documents"]
    assert [document["title"] for document in documents] == [
        "other-notes", "changed-target-title",
    ]
    assert all(document["category"] == "guide" for document in documents)
    for domain in rep.domains:
        failures = [check for check in domain.checks
                    if not check.ok and check.step == "list_filtered"]
        assert len(failures) == 1
        assert "collection='documents'" in failures[0].detail
        assert "expected_count=1 actual_count=0" in failures[0].detail


def test_failure_assertion_kills_accepted_rejection_mutant_in_both_projections():
    rejected_adapters = build_adapters(DocumentRestApp())
    rejected_report = runner.run_scenario(
        REJECTION_SCENARIO,
        rejected_adapters,
        projections=("backend", "contract"),
    )
    rejected_recording = rejected_report.domains[0].provider_recordings[0]

    assert rejected_report.status == PASSED
    assert rejected_adapters.normalizer.normalize(rejected_recording).succeeded is False
    assert {domain.projection: domain.status for domain in rejected_report.domains} == {
        "backend": PASSED,
        "contract": PASSED,
    }

    accepted_adapters = build_adapters(AcceptedRejectionApp())
    accepted_report = runner.run_scenario(
        REJECTION_SCENARIO,
        accepted_adapters,
        projections=("backend", "contract"),
    )
    accepted_recording = accepted_report.domains[0].provider_recordings[0]

    assert accepted_adapters.normalizer.normalize(accepted_recording).succeeded is True
    assert accepted_report.status == FAILED
    assert {domain.projection: domain.status for domain in accepted_report.domains} == {
        "backend": FAILED,
        "contract": FAILED,
    }
    failures = [
        check.detail
        for domain in accepted_report.domains
        for check in domain.checks
        if not check.ok
    ]
    assert len(failures) == 2
    assert all("expected failure" in detail for detail in failures)


def test_document_normalizer_treats_an_empty_204_as_success_with_no_fields():
    app = DocumentRestApp()
    adapters = build_adapters(app)
    session = adapters.auth.session("editor").credentials
    created = adapters.api.send(
        ports.RequestSpec(
            method="POST",
            path="/v3/documents",
            body={"title": "temporary", "category": "guide"},
        ),
        session,
    )
    document_id = adapters.normalizer.normalize(created).fields["document_id"]
    deleted = adapters.api.send(
        ports.RequestSpec(method="DELETE", path=f"/v3/documents/{document_id}"),
        session,
    )
    result = adapters.normalizer.normalize(deleted)

    assert deleted.status == 204
    assert result.succeeded is True
    assert result.fields == {}


def test_second_adapter_implements_only_the_three_intended_ports():
    adapter_classes = [
        value
        for module in (api, auth, normalizer)
        for value in vars(module).values()
        if inspect.isclass(value) and value.__module__ == module.__name__
    ]
    implemented_ports = {
        port_type
        for adapter_class in adapter_classes
        for port_type in (
            ports.Authenticator,
            ports.ApiDriver,
            ports.ResponseNormalizer,
            ports.StateProbe,
            ports.UiDriver,
            ports.StepwiseUiDriver,
        )
        if issubclass(adapter_class, port_type)
    }

    adapters = build_adapters(DocumentRestApp())
    assert implemented_ports == {
        ports.Authenticator,
        ports.ApiDriver,
        ports.ResponseNormalizer,
    }
    assert adapters.state is None
    assert adapters.ui is None


def test_explicit_document_response_normalizes_observed_fields():
    response_normalizer = normalizer.DocumentResponseNormalizer()
    # Independent observed input; never derive a response from Scenario checks.
    body = {"receipt": {"state": "accepted"}, "resource": {"document": {
        "identifier": "document-sample", "properties": {"category": "guide"}}}}
    response = ports.RecordedResponse(
        status=200,
        headers={},
        json=body,
        text="",
        trace_id=None,
        request=ports.RequestSpec(method="GET", path="documents/sample"),
    )

    result = response_normalizer.normalize(response)
    assert result.succeeded is True
    assert result.fields == {"document_id": "document-sample", "category": "guide"}

    partial_response = ports.RecordedResponse(
        status=200,
        headers={},
        json={
            "receipt": {"state": "accepted"},
            "resource": {"document": {"properties": {"title": "partial"}}},
        },
        text="",
        trace_id=None,
        request=ports.RequestSpec(method="GET", path="documents/sample"),
    )
    partial = response_normalizer.normalize(partial_response)
    assert partial.succeeded is True
    assert partial.fields == {"title": "partial"}


def _normalize_result_set(result_set):
    return normalizer.DocumentResponseNormalizer().normalize(ports.RecordedResponse(
        status=200,
        headers={},
        json={"receipt": {"state": "accepted"}, "result_set": result_set},
        text="",
        trace_id=None,
        request=ports.RequestSpec(method="GET", path="documents/search"),
    ))


def test_document_collection_mapping_preserves_order_duplicates_and_page_scope():
    first = {"identifier": "document-2", "properties": {"title": "second", "category": "guide"}}
    second = {"identifier": "document-1", "properties": {"title": "first", "category": "guide"}}
    result_set = {"nodes": [first, second, first], "page_info": {"next_cursor": 3}}
    before = deepcopy(result_set)

    result = _normalize_result_set(result_set)

    assert result.fields == {
        "documents": [
            {"document_id": "document-2", "title": "second", "category": "guide"},
            {"document_id": "document-1", "title": "first", "category": "guide"},
            {"document_id": "document-2", "title": "second", "category": "guide"},
        ],
        "returned": 3,
        "next_cursor": 3,
    }
    assert result_set == before
    assert "document_id" not in result.fields
    assert "title" not in result.fields


def test_document_collection_missing_is_not_an_empty_page():
    result = _normalize_result_set({"page_info": {"next_cursor": None}})
    assert "documents" not in result.fields
    assert "returned" not in result.fields


@pytest.mark.parametrize("nodes", [None, "not-a-list", {"identifier": "document-1"}, 0, False])
def test_document_collection_preserves_non_list_evidence(nodes):
    result = _normalize_result_set({"nodes": nodes})
    assert result.fields["documents"] is nodes
    assert "returned" not in result.fields


@pytest.mark.parametrize("malformed", [None, "not-an-object", 0, False, []])
def test_document_collection_does_not_filter_malformed_members(malformed):
    result = _normalize_result_set({"nodes": [
        {"identifier": "document-1", "properties": {"title": "present"}}, malformed,
    ]})
    assert result.fields["documents"] == [
        {"document_id": "document-1", "title": "present"}, malformed,
    ]
    assert result.fields["documents"][1] is malformed
    assert result.fields["returned"] == 2


def test_document_collection_empty_page_remains_present_and_empty():
    result = _normalize_result_set({"nodes": []})
    assert result.fields == {"documents": [], "returned": 0, "next_cursor": None}
