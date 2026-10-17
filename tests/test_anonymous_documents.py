"""Mixed participants against actual public Documents authorization decisions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from adapters.documents.api import DocumentApiDriver
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parents[1] / "examples/documents/scenarios"
CHILD = ROOT / "shared/access_document.yaml"
PROJECTIONS = [("backend", "contract"), ("e2e",)]


def write_yaml(path, declaration):
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


def document(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def copy_parent(tmp_path, participant, change_parent=None, change_child=None):
    parent = document(ROOT / f"mapped_{participant}_access.yaml")
    child = document(CHILD)
    if change_parent is not None:
        change_parent(parent)
    if change_child is not None:
        change_child(child)
    child_path = write_yaml(tmp_path / "child.yaml", child)
    path = write_yaml(tmp_path / "parent.yaml", parent)
    path.with_suffix(".includes.json").write_text(json.dumps({
        "manifest_version": 1,
        "scenarios": {child["scenario"]: {"path": "child.yaml",
            "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}},
    }), encoding="utf-8")
    return path


def profile_step(step_id, user=None, status=200, expected_code=None):
    step = {"id": step_id,
            "do": {"request": {"method": "GET", "path": ["account", "profile"]}},
            "expect": {"response": [{"check": "status_equals", "value": status}]}}
    if user is not None:
        step["user"] = user
    if expected_code is not None:
        step["expect"]["response"].append({
            "check": "field_equals", "field": "error_code", "value": expected_code})
    return step


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("participant,status,code,reader,generation", [
    ("peer", 403, "owner_required", "peer", 1),
    ("anonymous", 401, "session_required", None, 0),
])
def test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant(
        projections, participant, status, code, reader, generation):
    child_before = CHILD.read_bytes()
    path = ROOT / f"mapped_{participant}_access.yaml"
    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(path, adapters, projections=projections)
    domain = report.domains[0]
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert [item.status for item in domain.provider_recordings] == [201, 200, status, status, 200]
    assert [step.user for step in domain.steps] == ["creator", "creator", reader, reader, "creator"]
    assert [step.session_generation for step in domain.steps] == [1, 1, generation, generation, 1]
    assert [record.user for record in domain.provider_recordings] == [
        "creator", "creator", reader, reader, "creator"]
    assert app.request_count == 5  # Contract neither authenticates nor sends.
    assert len(app.authentications) == (2 if participant == "peer" else 1)
    assert app.requests[0][3] == app.requests[1][3] == app.requests[-1][3]
    assert app.requests[2][3] == app.requests[3][3] != app.requests[0][3]
    if participant == "anonymous":
        assert app.requests[2][3] == {"x-session-key": ""}
    else:
        assert app.authentications[0][0] != app.authentications[1][0]
    assert app.requests[1][1] == app.requests[2][1] == app.requests[3][1] == app.requests[4][1]
    refusal = domain.provider_recordings[3]
    assert refusal.json["fault"]["code"] == code
    assert adapters.normalizer.normalize(refusal).fields["error_code"] == code
    assert report.source_lookup["access/reader_denied"]["source_user"] == "reader"
    assert report.source_lookup["access/reader_denied"]["effective_user"] == (reader or "anonymous")
    for step in domain.steps[1:]:
        assert step.binding_sources
        for source in step.binding_sources.values():
            assert source.origin.step_id == "access/create"
            assert source.origin.user == "creator" and source.origin.session_generation == 1
    for principal, token in app.authentications:
        assert principal not in repr(report) and token not in repr(report)
    assert CHILD.read_bytes() == child_before


def test_two_maintained_callers_pin_exactly_the_same_unchanged_child():
    dependencies = []
    for participant in ("peer", "anonymous"):
        path = ROOT / f"mapped_{participant}_access.yaml"
        manifest = json.loads(path.with_suffix(".includes.json").read_text(encoding="utf-8"))
        dependencies.append(manifest["scenarios"]["documents.shared_access"])
        assert load_scenario(path).users == ["creator", participant]
    assert dependencies[0] == dependencies[1] == {
        "path": "shared/access_document.yaml", "sha256": hashlib.sha256(CHILD.read_bytes()).hexdigest()}
    assert load_scenario(CHILD).users == ["creator", "reader"]


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("participant,status,code", [
    ("peer", 403, "owner_required"), ("anonymous", 401, "session_required")])
def test_fixed_403_child_is_not_relaxed_by_anonymous_mapping(tmp_path, projections, participant, status, code):
    def require_ownership_refusal(child):
        child["steps"][-1]["expect"]["response"] = [
            {"check": "status_equals", "value": 403}, {"check": "failure"},
            {"check": "field_equals", "field": "error_code", "value": "owner_required"},
        ]

    path = copy_parent(tmp_path, participant, change_child=require_ownership_refusal)
    app = DocumentRestApp()
    report = run_scenario(path, build_adapters(app), projections=projections)
    domain = report.domains[0]
    assert domain.provider_recordings[2].status == status
    assert domain.provider_recordings[2].json["fault"]["code"] == code
    assert [step.status for step in domain.steps] == [
        "PASSED", "PASSED", "PASSED" if participant == "peer" else "FAILED", "PASSED", "PASSED"]
    assert report.status == ("PASSED" if participant == "peer" else "FAILED")
    assert app.request_count == 5
    if participant == "anonymous":
        failed = [check for check in domain.steps[2].checks if not check.ok]
        assert {check.check for check in failed} == {"status_equals", "field_equals"}
        assert domain.steps[-1].after_failures == ["access/reader_denied"]


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("participant", ["peer", "anonymous"])
def test_explicit_map_and_handwritten_flat_flow_have_equivalent_observations(tmp_path, projections, participant):
    parent = document(ROOT / f"mapped_{participant}_access.yaml")
    child = document(CHILD)
    local_steps = deepcopy(child["steps"])
    for step in local_steps:
        if step["user"] == "reader":
            step["user"] = participant

    def replace_result(node):
        if isinstance(node, list):
            return [replace_result(item) for item in node]
        if not isinstance(node, dict):
            return node
        if node.get("from_step") == "access" and "result" in node:
            return {"from_step": "create", "response_field": {
                "document_id": "document_id", "created_title": "title"}[node["result"]]}
        return {key: replace_result(value) for key, value in node.items()}

    parent["scenario"] = "documents.flat_access"
    parent["steps"] = local_steps + replace_result(parent["steps"][1:])
    flat_path = write_yaml(tmp_path / "flat.yaml", parent)
    reports, targets = [], []
    for path in (ROOT / f"mapped_{participant}_access.yaml", flat_path):
        app = DocumentRestApp()
        reports.append(run_scenario(path, build_adapters(app), projections=projections))
        targets.append(app)
    assert [report.status for report in reports] == ["PASSED", "PASSED"]
    observations = []
    for report in reports:
        observations.append([
            (domain.projection, [(step.status, step.user, step.session_generation,
                [(check.point, check.check, check.ok) for check in step.checks])
                for step in domain.steps],
             [(record.status, record.json) for record in domain.provider_recordings])
            for domain in report.domains])
    assert observations[0] == observations[1]
    assert [[(method, path, body) for method, path, body, _ in app.requests]
            for app in targets][0] == [
                (method, path, body) for method, path, body, _ in targets[1].requests]


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("participant", ["peer", "anonymous"])
def test_named_result_query_survives_user_mapping_and_real_filtering(tmp_path, projections, participant):
    def expose_observed_category(child):
        child["steps"][0]["expect"]["response"].append({"check": "has", "field": "category"})
        child["results"]["created_category"] = {"from_step": "create", "response_field": "category"}

    def use_query(parent):
        # Both users consume the same observed category; no implicit resolver default.
        category = {"from_step": "access", "result": "created_category"}
        parent["steps"][1]["do"]["request"]["query"] = {"category": dict(category)}
        parent["steps"][-1]["do"]["request"] = {
            "method": "GET", "path": ["documents", "search"],
            "query": {"category": dict(category), "limit": 1, "cursor": 0}}
        parent["steps"][-1]["expect"]["response"] = [
            {"check": "status_equals", "value": 200},
            {"check": "collection_matching_count", "field": "documents", "count": 1,
             "matching": {"document_id": {"from_step": "access", "result": "document_id"},
                          "category": dict(category)}},
        ]

    path = copy_parent(tmp_path, participant, change_parent=use_query, change_child=expose_observed_category)
    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert adapters.api.sent[-2].query == {"category": "guide"}
    assert adapters.api.sent[-1].query == {"category": "guide", "limit": "1", "cursor": "0"}
    assert app.requests[-2][1] == "/v3/documents/document-1?category=guide"
    assert app.requests[-1][1] == "/v3/documents?category=guide&limit=1&cursor=0"
    final = report.domains[0].steps[-1]
    assert any(source.response_field == "category" for source in final.binding_sources.values())
    assert all(source.origin.user == "creator" and source.origin.session_generation == 1
               for source in final.binding_sources.values())


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("users", [[], ["anonymous"]])
def test_implicit_or_declared_anonymous_needs_no_authenticator(tmp_path, projections, users):
    path = write_yaml(tmp_path / "anonymous.yaml", {
        "schema_version": 1, "scenario": "documents.anonymous_only", "users": users,
        "steps": [profile_step("profile", status=401, expected_code="session_required")]})
    app = DocumentRestApp()
    adapters = build_adapters(app)
    adapters.auth = None
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert app.authentications == []
    assert app.requests[0][3] == {"x-session-key": ""}
    step = report.domains[0].steps[0]
    assert step.user is None and step.session_generation == 0


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_anonymous_response_reference_preserves_origin_and_named_session(tmp_path, projections):
    steps = [profile_step("named_before", "creator"),
             profile_step("anonymous_first", "anonymous", 401, "session_required"),
             profile_step("anonymous_second", "anonymous", 401,
                          {"from_step": "anonymous_first", "response_field": "error_code"}),
             profile_step("named_after", "creator")]
    path = write_yaml(tmp_path / "mixed.yaml", {"schema_version": 1,
        "scenario": "documents.anonymous_origin", "users": ["creator", "anonymous"], "steps": steps})
    app = DocumentRestApp()
    report = run_scenario(path, build_adapters(app), projections=projections)
    assert report.status == "PASSED", report.localize()
    assert len(app.authentications) == 1 and app.request_count == 4
    assert app.requests[0][3] == app.requests[3][3] != app.requests[1][3]
    second = report.domains[0].steps[2]
    assert second.user is None and second.session_generation == 0
    assert len(second.binding_sources) == 1
    source = next(iter(second.binding_sources.values()))
    assert source.origin.step_id == "anonymous_first"
    assert source.origin.user is None and source.origin.session_generation == 0
    assert source.origin.is_final is True


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_distinct_aliases_cannot_hide_one_account_before_any_target_action(projections):
    app = DocumentRestApp()
    adapters = build_adapters(app)
    original = adapters.auth.identify
    adapters.auth.identify = lambda user: original("creator")
    report = run_scenario(ROOT / "mapped_peer_access.yaml", adapters, projections=projections)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["ERROR"] + ["BLOCKED"] * 4
    assert app.request_count == 0 and app.authentications == []


class LeakingCredentialsDriver(DocumentApiDriver):
    """Negative control: a transport incorrectly retains the previous credentials."""

    def __init__(self, app):
        super().__init__(app)
        self.previous = None

    def send(self, spec, session):
        if session is not None:
            self.previous = session
        return super().send(spec, session if session is not None else self.previous)


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_anonymous_label_does_not_prove_unauthenticated_target_request(projections):
    app = DocumentRestApp()
    adapters = build_adapters(app)
    adapters.api = LeakingCredentialsDriver(app)
    report = run_scenario(ROOT / "mapped_anonymous_access.yaml", adapters, projections=projections)
    assert report.status == "FAILED"
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "FAILED", "FAILED", "PASSED"]
    assert [record.status for record in domain.provider_recordings] == [201, 200, 200, 200, 200]
    assert app.requests[1][3] == app.requests[2][3] == app.requests[3][3]
    assert domain.steps[2].user is None  # A label is not independent identity proof.


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_mapped_anonymous_cannot_silently_ignore_child_reauthentication(tmp_path, projections):
    path = copy_parent(tmp_path, "anonymous", change_child=lambda child:
        child["steps"][-1].update({"session": "new"}))
    app = DocumentRestApp()
    with pytest.raises(DeclarationError):
        run_scenario(path, build_adapters(app), projections=projections)
    assert app.request_count == 0 and app.authentications == []


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_mapped_child_failure_stop_keeps_later_steps_unexecuted(tmp_path, projections):
    def stop_on_named_only_refusal(child):
        child["steps"][-1]["on_failure"] = "stop"
        child["steps"][-1]["expect"]["response"] = [{"check": "status_equals", "value": 403}]

    path = copy_parent(tmp_path, "anonymous", change_child=stop_on_named_only_refusal)
    app = DocumentRestApp()
    report = run_scenario(path, build_adapters(app), projections=projections)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == [
        "PASSED", "PASSED", "FAILED", "BLOCKED", "BLOCKED"]
    assert app.request_count == 3 and len(app.authentications) == 1
    assert all(step.session_generation is None for step in report.domains[0].steps[-2:])


def test_documented_include_fragment_uses_its_real_pinned_child(tmp_path):
    root = Path(__file__).resolve().parents[1]
    text = (root / "SCENARIO.md").read_text(encoding="utf-8")
    fragment = next(block.split("```", 1)[0] for block in text.split("```yaml\n")[1:]
                    if block.startswith("- id: access\n"))
    parent = {"schema_version": 1, "scenario": "documents.documented_mapping",
              "users": ["creator", "anonymous"], "steps": yaml.safe_load(fragment)}
    child = tmp_path / "child.yaml"
    child.write_bytes(CHILD.read_bytes())
    path = write_yaml(tmp_path / "parent.yaml", parent)
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {"documents.shared_access": {"path": "child.yaml",
            "sha256": hashlib.sha256(child.read_bytes()).hexdigest()}}}), encoding="utf-8")
    report = run_scenario(path, build_adapters(DocumentRestApp()), projections=("backend", "contract"))
    assert report.status == "PASSED", report.localize()
