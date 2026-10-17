"""Real synthetic account enforcement, not responses inferred from assertions."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parents[1] / "examples/documents/scenarios"


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_owner_reads_and_distinct_same_role_peer_is_denied(projections):
    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(ROOT / "owner_peer.yaml", adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    domain = report.domains[0]
    assert [record.status for record in domain.provider_recordings] == [200, 201, 200, 200, 403]
    assert [step.user for step in domain.steps] == ["creator", "creator", "creator", "peer", "peer"]
    assert [step.session_generation for step in domain.steps] == [1] * 5
    assert len(app.authentications) == 2
    assert app.authentications[0][0] != app.authentications[1][0]
    assert app.authentications[0][1] != app.authentications[1][1]
    assert app.request_count == 5  # Offline contract does not authenticate or issue requests.
    owner_headers, peer_headers = app.requests[2][3], app.requests[4][3]
    assert owner_headers != peer_headers
    assert app.requests[2][1] == app.requests[4][1]
    normalized = [adapters.normalizer.normalize(record) for record in domain.provider_recordings]
    assert normalized[0].fields["role"] == normalized[3].fields["role"] == "member"
    assert normalized[2].fields["document_id"] == normalized[1].fields["document_id"]
    assert normalized[4].fields["error_code"] == "owner_required"
    assert report.source_lookup["setup/create"]["source_user"] == "operator"
    assert report.source_lookup["setup/create"]["effective_user"] == "creator"
    for principal, token in app.authentications:
        assert principal not in repr(report)
        assert token not in repr(report)


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
@pytest.mark.parametrize("permission_policy,expected_old", [("live", "PASSED"), ("session", "FAILED")])
def test_permission_change_old_session_then_reauthenticate_same_account(
        projections, permission_policy, expected_old):
    app = DocumentRestApp(permission_policy=permission_policy)
    adapters = build_adapters(app)
    report = run_scenario(ROOT / "permission_sessions.yaml", adapters, projections=projections)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED"] * 4 + [expected_old, "PASSED"]
    assert report.status == ("PASSED" if expected_old == "PASSED" else "FAILED")
    assert [step.user for step in domain.steps] == ["member"] * 3 + ["administrator", "member", "member"]
    assert [step.session_generation for step in domain.steps] == [1, 1, 1, 1, 1, 2]
    assert len(app.authentications) == 3 and app.request_count == 6
    first, administrator, refreshed = app.authentications
    assert first[0] == refreshed[0] != administrator[0]
    assert first[1] != refreshed[1]
    assert app.requests[0][3] == app.requests[2][3] == app.requests[4][3]
    assert app.requests[5][3] != app.requests[4][3]
    assert app.requests[3][0] == "PATCH" and app.requests[3][2] == {"read_documents": False}
    assert app._accounts["member"]["read_documents"] is False  # Login never grants access back.
    assert domain.provider_recordings[-1].status == 403
    assert domain.steps[-1].after_failures == ([] if expected_old == "PASSED" else ["old_session"])
    for source in domain.steps[-1].binding_sources.values():
        assert source.origin.user == "member" and source.origin.session_generation == 1


def _write(tmp_path, document):
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_anonymous_real_target_does_not_reuse_preexisting_authenticated_account(tmp_path, projections):
    app = DocumentRestApp()
    adapters = build_adapters(app)
    previous = adapters.auth.session("creator")
    path = _write(tmp_path, {"schema_version": 1, "scenario": "documents.anonymous", "users": [],
        "steps": [{"id": "profile", "do": {"request": {"method": "GET", "path": ["account", "profile"]}},
                   "expect": {"response": [{"check": "status_equals", "value": 401}, {"check": "failure"}]}}]})
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert len(app.authentications) == 1
    assert app.requests[0][3] == {"x-session-key": ""}
    assert previous.authentication_id not in repr(report)


def test_two_parent_users_reuse_exact_child_bytes_with_independent_ownership(tmp_path):
    child_bytes = (ROOT / "shared/create_document.yaml").read_bytes()
    child = tmp_path / "child.yaml"
    child.write_bytes(child_bytes)
    steps = []
    for user in ("creator", "peer"):
        steps.extend([
            {"id": f"create_{user}", "user": user, "do": {"include": "documents.shared_create"},
             "with": {"document_title": f"Document for {user}"}},
            {"id": f"read_{user}", "user": user, "do": {"request": {"method": "GET", "path": [
                "documents", {"from_step": f"create_{user}", "result": "document_id"}]}},
             "expect": {"response": [{"check": "status_equals", "value": 200},
                 {"check": "field_equals", "field": "title", "value": f"Document for {user}"}]}}])
    path = _write(tmp_path, {"schema_version": 1, "scenario": "documents.reused", "users": ["creator", "peer"], "steps": steps})
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1, "scenarios": {
        "documents.shared_create": {"path": "child.yaml", "sha256": hashlib.sha256(child_bytes).hexdigest()}}}), encoding="utf-8")
    app = DocumentRestApp()
    report = run_scenario(path, build_adapters(app), projections=("backend", "contract"))
    assert report.status == "PASSED", report.localize()
    assert child.read_bytes() == child_bytes
    assert app._owners == {"document-1": "account-creator", "document-2": "account-peer"}
    assert [step.user for step in report.domains[0].steps] == ["creator", "creator", "peer", "peer"]


def test_reused_principal_configuration_fails_before_document_business_actions():
    app = DocumentRestApp()
    adapters = build_adapters(app)
    original_identify = adapters.auth.identify
    adapters.auth.identify = lambda user: original_identify("creator")
    report = run_scenario(ROOT / "owner_peer.yaml", adapters, projections=("backend",))
    assert [step.status for step in report.domains[0].steps] == ["ERROR"] + ["BLOCKED"] * 4
    assert app.request_count == 0 and app.authentications == []
