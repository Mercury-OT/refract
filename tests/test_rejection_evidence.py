"""Bounded rejection controls through the real public Documents pipeline."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from adapters.documents.api import DocumentApiDriver
from adapters.documents.normalizer import DocumentResponseNormalizer
from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/documents/scenarios/owner_access.yaml"
PROJECTIONS = [("backend", "contract"), ("e2e",)]
MISSING = object()
SENSITIVE = "private-rejection-detail-sentinel"


def _write_variant(tmp_path, change):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def _run(app, projections, path=EXAMPLE, **kwargs):
    adapters = build_adapters(app)
    report = run_scenario(path, adapters, projections=projections, **kwargs)
    return adapters, report, report.domains[0]


def _checks(step):
    return {check.check: check.ok for check in step.checks}


def _assert_final_reached(app, domain):
    assert [step.status for step in domain.steps[:3]] == ["PASSED"] * 3
    assert app.request_count == 4
    assert [response.status for response in domain.provider_recordings[:3]] == [201, 200, 200]
    document_id = domain.provider_recordings[0].json["resource"]["document"]["identifier"]
    assert app.requests[1][1] == app.requests[3][1] == f"/v3/documents/{document_id}"
    assert app.requests[2][1] == "/v3/account/profile"
    assert app.requests[2][3] == app.requests[3][3]  # Same peer session, no refresh.
    assert len(app.authentications) == 2


def _assert_sensitive_repr_hidden(app, report, *extra):
    views = [repr(report)]
    for domain in report.domains:
        views.append(repr(domain))
        views.extend(repr(step) for step in domain.steps)
        views.extend(repr(check) for check in domain.checks)
    for value in [item for pair in app.authentications for item in pair] + list(extra):
        assert all(value not in view for view in views)


class InvalidPeerSession(DocumentRestApp):
    """Revoke the real token at one specified boundary, not the expected result."""

    def __init__(self, when):
        super().__init__()
        self.when = when
        self.invalidations = 0

    def handle(self, method, path, body=None, headers=None):
        profile = method == "GET" and path == "/v3/account/profile"
        if profile and self.when == "before":
            self._sessions.pop(headers["x-session-key"])
            self.invalidations += 1
        response = super().handle(method, path, body, headers)
        if profile and self.when == "after":
            assert response.status == 200
            self._sessions.pop(headers["x-session-key"])
            self.invalidations += 1
        return response


class InvalidCreation(DocumentRestApp):
    """Send a missing title through the real application's input validator."""

    def __init__(self):
        super().__init__()
        self.injections = 0

    def handle(self, method, path, body=None, headers=None):
        if method == "POST" and path == "/v3/documents":
            body = deepcopy(body)
            del body["title"]
            self.injections += 1
        return super().handle(method, path, body, headers)


class ChangedPeerReason(DocumentRestApp):
    """Alter only the genuine ownership refusal, retaining its actual 403."""

    def __init__(self, code=MISSING, *, remove_fault=False):
        super().__init__()
        self.code = code
        self.remove_fault = remove_fault
        self.injections = 0
        self.original = None

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if response.status != 403 or response.body["fault"]["code"] != "owner_required":
            return response
        assert method == "GET" and path.startswith("/v3/documents/")
        self.injections += 1
        self.original = deepcopy(response.body)
        changed = deepcopy(response.body)
        if self.remove_fault:
            del changed["fault"]
        elif self.code is MISSING:
            del changed["fault"]["code"]
        else:
            changed["fault"]["code"] = self.code
        return RestResponse(response.status, changed, response.headers)


def test_approved_file_loads_without_new_syntax_or_hidden_steps():
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    scenario = load_scenario(EXAMPLE)
    assert raw["schema_version"] == 1
    assert raw["users"] == ["creator", "peer"]
    assert raw["parameters"] == {"document_title": "Permission review document"}
    assert [step.id for step in scenario.steps] == ["create", "creator_reads", "peer_profile", "peer_reads"]
    assert [step.user for step in scenario.steps] == ["creator", "creator", "peer", "peer"]
    assert all(set(step["do"]) == {"request"} for step in raw["steps"])
    assert all(step.get("on_failure") == "stop" for step in raw["steps"][:3])
    assert "on_failure" not in raw["steps"][-1]
    assert all("session" not in step and set(step["expect"]) == {"response"} for step in raw["steps"])
    assert raw["steps"][-1]["expect"]["response"] == [
        {"check": "status_equals", "value": 403}, {"check": "failure"},
        {"check": "field_equals", "field": "error_code", "value": "owner_required"}]


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_approved_example_uses_actual_identity_sessions_and_reason(projections):
    app = DocumentRestApp()
    _, report, domain = _run(app, projections)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert [step.status for step in domain.steps] == ["PASSED"] * 4
    assert [response.status for response in domain.provider_recordings] == [201, 200, 200, 403]
    _assert_final_reached(app, domain)
    assert app.authentications[0][0] != app.authentications[1][0]
    assert app.authentications[0][1] != app.authentications[1][1]
    assert app.requests[0][3] == app.requests[1][3] != app.requests[2][3]
    assert [step.session_generation for step in domain.steps] == [1] * 4
    assert _checks(domain.steps[-1]) == {"status_equals": True, "failure": True, "field_equals": True}
    assert domain.provider_recordings[-1].json["fault"]["code"] == "owner_required"
    assert all(result.status == "PASSED" for result in report.domains)
    _assert_sensitive_repr_hidden(app, report)


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("when", ["before", "after"])
def test_invalid_peer_session_cannot_be_counted_as_ownership_denial(projections, when):
    app = InvalidPeerSession(when)
    _, report, domain = _run(app, projections)
    assert app.invalidations == 1
    assert report.status == "FAILED"
    assert len(app.authentications) == 2  # Neither path silently reauthenticates.
    assert domain.provider_recordings[-1].status == 401
    assert domain.provider_recordings[-1].json["fault"]["code"] == "session_required"
    if when == "before":
        assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "FAILED", "BLOCKED"]
        assert app.request_count == 3
        assert app.requests[-1][1] == "/v3/account/profile"
        assert _checks(domain.steps[2]) == {"status_equals": False, "success": False}
        assert domain.steps[3].checks == []
        assert domain.steps[3].blocked_by == ["peer_profile"]
    else:
        _assert_final_reached(app, domain)
        assert domain.steps[-1].status == "FAILED"
        assert _checks(domain.steps[-1]) == {"status_equals": False, "failure": True, "field_equals": False}
    _assert_sensitive_repr_hidden(app, report)


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_real_input_validation_stops_the_permission_test(projections):
    app = InvalidCreation()
    adapters, report, domain = _run(app, projections)
    assert app.injections == 1 and app.request_count == 1
    assert adapters.api.sent[0].body["title"] == "Permission review document"
    assert "title" not in app.requests[0][2]  # The fault really reached target validation.
    assert app._documents == {} and len(app.authentications) == 1
    assert domain.provider_recordings[0].status == 400
    assert domain.provider_recordings[0].json["fault"]["code"] == "title_required"
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["FAILED", "BLOCKED", "BLOCKED", "BLOCKED"]
    assert not _checks(domain.steps[0])["status_equals"]
    assert all(step.checks == [] and step.blocked_by == ["create"] for step in domain.steps[1:])


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("code", [
    pytest.param(MISSING, id="missing"), None, "unknown_reason", "session_required",
    "title_required", "read_permission_required", "administrator_required",
    False, True, 0, 1, ["owner_required"], {"code": "owner_required"}, "owner_required",
])
def test_same_403_with_missing_confused_or_wrong_type_reason(projections, code):
    app = ChangedPeerReason(code)
    adapters, report, domain = _run(app, projections)
    _assert_final_reached(app, domain)
    assert app.injections == 1 and app.original["fault"]["code"] == "owner_required"
    record = domain.provider_recordings[-1]
    assert record.status == 403
    norm = adapters.normalizer.normalize(record)
    assert norm.succeeded is False
    if code is MISSING:
        assert "code" not in record.json["fault"]
        assert norm.fields["error_code"] is None
    else:
        assert type(record.json["fault"]["code"]) is type(code)
        assert record.json["fault"]["code"] == code
        assert type(norm.fields["error_code"]) is type(code)
        assert norm.fields["error_code"] == code
    expected_ok = type(code) is str and code == "owner_required"
    assert _checks(domain.steps[-1]) == {"status_equals": True, "failure": True, "field_equals": expected_ok}
    assert report.status == ("PASSED" if expected_ok else "FAILED")
    assert domain.steps[-1].status == report.status
    if not expected_ok:
        assert (projections[0], "peer_reads", "response", "field_equals") in [item[:4] for item in report.localize()]
    if "contract" in projections:
        assert report.domains[1].status == report.status


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_removing_only_reason_check_demonstrates_ambiguous_403_false_positive(tmp_path, projections):
    original = EXAMPLE.read_bytes()
    weak = _write_variant(tmp_path, lambda raw: raw["steps"][-1]["expect"]["response"].pop())
    strong_app, weak_app = ChangedPeerReason(remove_fault=True), ChangedPeerReason(remove_fault=True)
    _, strong, strong_domain = _run(strong_app, projections)
    _, weaker, weak_domain = _run(weak_app, projections, weak)
    _assert_final_reached(strong_app, strong_domain)
    _assert_final_reached(weak_app, weak_domain)
    assert strong_app.injections == weak_app.injections == 1
    assert strong_domain.provider_recordings[-1].json == weak_domain.provider_recordings[-1].json == {"receipt": {"state": "rejected"}}
    assert _checks(strong_domain.steps[-1]) == {"status_equals": True, "failure": True, "field_equals": False}
    assert _checks(weak_domain.steps[-1]) == {"status_equals": True, "failure": True}
    assert strong.status == "FAILED" and weaker.status == "PASSED"
    assert EXAMPLE.read_bytes() == original


@pytest.mark.parametrize("fault,expected", [
    ({"code": "owner_required"}, {"error_code": "owner_required", "error_message": None}),
    ({}, {"error_code": None, "error_message": None}),
    ({"code": None}, {"error_code": None, "error_message": None}),
    ({"code": ["owner_required"]}, {"error_code": ["owner_required"], "error_message": None}),
    ({"code": False}, {"error_code": False, "error_message": None}),
    (None, {}), (["owner_required"], {}), ("owner_required", {}),
])
def test_normalizer_faithfully_extracts_raw_reason_without_classifying_status(fault, expected):
    raw = ports.RecordedResponse(403, {}, {"receipt": {"state": "rejected"}, "fault": fault},
                                 "", None, ports.RequestSpec("GET", "/v3/documents/document-1"))
    observed = DocumentResponseNormalizer().normalize(raw)
    assert observed.succeeded is False and observed.status == 403
    assert observed.fields == expected
    if "error_code" in expected:
        assert type(observed.fields["error_code"]) is type(expected["error_code"])
    assert observed.raw is raw


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_execution_error_is_not_a_business_denial(projections):
    class BrokenTransport(DocumentApiDriver):
        attempts = 0

        def send(self, spec, session):
            self.attempts += 1
            if spec.path == "/v3/account/profile":
                raise RuntimeError(f"transport failed: {SENSITIVE} {session['session_key']}")
            return super().send(spec, session)

    app = DocumentRestApp()
    adapters = build_adapters(app)
    adapters.api = BrokenTransport(app)
    report = run_scenario(EXAMPLE, adapters, projections=projections)
    domain = report.domains[0]
    assert adapters.api.attempts == 3 and app.request_count == 2
    assert len(app.authentications) == 2
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "ERROR", "BLOCKED"]
    assert domain.steps[2].checks == [] and domain.steps[3].checks == []
    assert SENSITIVE in domain.steps[2].detail
    _assert_sensitive_repr_hidden(app, report, SENSITIVE)


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("evidence", ["unavailable", "empty", "error"])
def test_separately_declared_state_obligation_is_never_a_silent_pass(tmp_path, projections, evidence):
    # A test-only additional obligation, not telemetry claimed by the example.
    path = _write_variant(tmp_path, lambda raw: raw["steps"][2]["expect"].update(
        backend_state=[{"check": "span_exists", "span": "session.accepted"}]))

    class StateProbe:
        calls = 0

        def observe(self, trace_id):
            self.calls += 1
            if evidence == "error":
                raise RuntimeError(SENSITIVE)
            return ports.StateFacts(trace_id, [])

    app = DocumentRestApp()
    adapters = build_adapters(app)
    probe = StateProbe()
    adapters.state = None if evidence == "unavailable" else probe
    clock = [0.0]
    report = run_scenario(path, adapters, projections=projections, now=lambda: clock[0],
                          sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    domain = report.domains[0]
    if evidence == "unavailable":
        assert report.status == "DEGRADED" and report.passed is True
        assert domain.steps[2].skipped and "StateProbe" in domain.steps[2].skipped[0]
        assert report.degradations()
        assert app.request_count == 4 and probe.calls == 0
    elif evidence == "empty":
        assert report.status == "FAILED" and probe.calls > 0
        assert _checks(domain.steps[2])["span_exists"] is False
        assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "FAILED", "BLOCKED"]
        assert app.request_count == 3
    else:
        assert report.status == "FAILED" and probe.calls == 1
        assert [step.status for step in domain.steps] == ["PASSED", "PASSED", "ERROR", "BLOCKED"]
        assert app.request_count == 3
        _assert_sensitive_repr_hidden(app, report, SENSITIVE)


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_wrong_reason_detail_is_not_exposed_by_default_report_repr(projections):
    app = ChangedPeerReason(SENSITIVE)
    _, report, domain = _run(app, projections)
    _assert_final_reached(app, domain)
    assert report.status == "FAILED"
    assert SENSITIVE in domain.steps[-1].checks[-1].detail
    _assert_sensitive_repr_hidden(app, report, SENSITIVE)
