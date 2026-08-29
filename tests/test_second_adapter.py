import inspect
from pathlib import Path

from refracto import ports, runner
from refracto.report import PASSED

from adapters.documents import api, auth, normalizer
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_ROOT = ROOT / "examples" / "documents"
HAPPY_SCENARIO = DOCUMENTS_ROOT / "scenarios" / "create_list_delete.yaml"
REJECTION_SCENARIO = DOCUMENTS_ROOT / "scenarios" / "rejected_create.yaml"


class AcceptedRejectionApp(DocumentRestApp):
    """A deliberate mutant proving the rejection outcome is not expressible."""

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if response.status != 422:
            return response
        mutated = dict(response.body)
        mutated["receipt"] = {"state": "accepted", "operation": "create"}
        return RestResponse(200, mutated, response.headers)


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
    assert len(adapters.api.sent) == 3
    assert adapters.api.sent[0].body == {"title": "field-notes", "category": "guide"}
    assert "category=guide" in adapters.api.sent[1].path
    assert "cursor=0" in adapters.api.sent[1].path
    assert "limit=1" in adapters.api.sent[1].path
    created_id = adapters.api.sent[2].path.rsplit("/", 1)[-1]
    assert created_id.startswith("document-")
    assert created_id not in adapters.api.sent[0].body.values()
    assert app.request_count == 3


def test_rejection_scenario_asserts_available_details_but_cannot_require_failure():
    rejected_adapters = build_adapters(DocumentRestApp())
    rejected_report = runner.run_scenario(
        REJECTION_SCENARIO,
        rejected_adapters,
        projections=("backend", "contract"),
    )
    rejected_recording = rejected_report.domains[0].provider_recordings[0]

    assert rejected_report.status == PASSED
    assert rejected_adapters.normalizer.normalize(rejected_recording).succeeded is False

    accepted_adapters = build_adapters(AcceptedRejectionApp())
    accepted_report = runner.run_scenario(
        REJECTION_SCENARIO,
        accepted_adapters,
        projections=("backend", "contract"),
    )
    accepted_recording = accepted_report.domains[0].provider_recordings[0]

    assert accepted_adapters.normalizer.normalize(accepted_recording).succeeded is True
    assert accepted_report.status == PASSED


def test_document_normalizer_treats_an_empty_204_as_success_with_no_fields():
    app = DocumentRestApp()
    adapters = build_adapters(app)
    session = adapters.auth.session("editor")
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


def test_synthesized_document_envelope_round_trips_declared_values():
    response_normalizer = normalizer.DocumentResponseNormalizer()
    body = response_normalizer.synthesize(
        {"document_id", "category"},
        {"document_id": "document-sample", "category": "guide"},
    )
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
