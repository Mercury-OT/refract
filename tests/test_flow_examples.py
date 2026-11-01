"""End-to-end public Flow consumer against the unchanged Documents target."""
import copy
from pathlib import Path
import shutil

import pytest
import yaml

from adapters.documents import build_adapters
from adapters.documents.normalizer import DocumentResponseNormalizer
from examples.documents.app import DocumentRestApp
from examples.flow.run_example import FLOW, run
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.runner import run_flow


def test_public_flow_runs_three_real_operations_with_one_current_session():
    report = run()
    assert report.status == "PASSED"
    assert report.degradations() == []
    assert [node.node_id for node in report.scenarios] == ["create", "update", "read"]
    assert all(node.status == "PASSED" for node in report.scenarios)
    backend = next(domain for domain in report.domains if domain.projection == "backend")
    records = backend.provider_recordings
    assert [record.request.method for record in records] == ["POST", "PATCH", "GET"]
    assert records[1].request.path == records[2].request.path
    assert all(step.user == "editor" and step.session_generation == 1 for step in backend.steps)
    assert report.scenarios[2].domains[0].flow_reads["content"].writer_node == "update"
    assert report.scenarios[2].domains[0].flow_reads["document_id"].writer_node == "create"


class StaleUpdateObservation(DocumentResponseNormalizer):
    """Labeled observation fault; target response and actual target remain intact."""

    def normalize(self, response):
        normalized = super().normalize(response)
        if response.request.method == "PATCH":
            normalized.fields["content"] = {"text": "Initial content"}
        return normalized


@pytest.mark.parametrize("policy", ["stop", "continue"])
def test_stale_update_cannot_publish_or_reuse_old_expected_content(tmp_path, policy):
    root = tmp_path / "flow"
    shutil.copytree(FLOW.parent, root, ignore=shutil.ignore_patterns("__pycache__"))
    path = root / FLOW.name
    declaration = yaml.safe_load(path.read_text())
    declaration["on_failure"] = policy
    path.write_text(yaml.safe_dump(declaration, sort_keys=False))
    app = DocumentRestApp()
    adapters = build_adapters(app)
    adapters.normalizer = StaleUpdateObservation()
    report = run_flow(path, adapters, projections=("backend", "contract"))
    assert report.status == "FAILED"
    assert report.scenarios[0].status == "PASSED"
    assert report.scenarios[1].status == "FAILED"
    assert report.scenarios[2].status != "PASSED"
    assert app.request_count == 2
    assert len(app.authentications) == 1
    assert all(step.status == "BLOCKED" for domain in report.scenarios[2].domains
               for step in domain.steps)
    for domain in report.scenarios[1].domains:
        assert not domain.flow_writes["content"].available
    # The retained initial value is diagnostic history, never a usable fallback.
    history = report.parameter_history["backend"]["content"]
    assert history[0].value == {"text": "Initial content"}
    assert history[-1].provenance.available is False
    assert "Initial content" not in repr(report)


@pytest.mark.parametrize("name", ["create_document.yaml", "update_document.yaml", "read_document.yaml"])
def test_flow_dependent_public_scenarios_reject_standalone_loading(name):
    with pytest.raises(DeclarationError):
        load_scenario(FLOW.with_name(name))


def test_public_flow_repeated_runs_do_not_reuse_response_or_authentication():
    app = DocumentRestApp()
    adapters = build_adapters(app)
    first = run_flow(FLOW, adapters, projections=("backend", "contract"))
    second = run_flow(FLOW, adapters, projections=("backend", "contract"))
    assert first.status == second.status == "PASSED"
    assert first.run_id != second.run_id
    assert app.request_count == 6
    assert len(app.authentications) == 2
    first_id = first.parameter_history["backend"]["document_id"][-1].value
    second_id = second.parameter_history["backend"]["document_id"][-1].value
    assert first_id != second_id
    assert first.scenarios[0].domains[0].flow_writes["document_id"].version == 1
    assert second.scenarios[0].domains[0].flow_writes["document_id"].version == 1


def test_flow_calls_preserve_input_files_and_declaration_initials():
    files = list(FLOW.parent.glob("*.yaml")) + list(FLOW.parent.glob("*.json"))
    before = {path: path.read_bytes() for path in files}
    app = DocumentRestApp()
    report = run_flow(FLOW, build_adapters(app), projections=("backend", "contract"))
    assert report.status == "PASSED"
    assert {path: path.read_bytes() for path in files} == before
    first = report.parameter_history["backend"]["content"][0]
    assert copy.deepcopy(first.value) == {"text": "Initial content"}
