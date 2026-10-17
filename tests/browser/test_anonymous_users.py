"""Real Chromium evidence for declared anonymous and named participants.

The public laboratory is an echo service, not an authorization implementation.
These tests prove credential/context isolation and attribution, not permissions.
"""
import dataclasses
import hashlib
import json
from types import SimpleNamespace

import pytest
import yaml

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from tests.browser.adapter import SyntheticUi
from tests.browser.test_support import fixture
from tests.fakes import FakeNormalizer


SECRET = "synthetic-account-credential-984"


class Accounts(ports.Authenticator):
    def __init__(self, origin):
        self.origin = origin
        self.identified, self.acquired = [], []

    def identify(self, user):
        assert user != "anonymous"
        self.identified.append(user)
        return "principal-" + user

    def session(self, user):
        assert user != "anonymous"
        self.acquired.append(user)
        identity = f"{SECRET}-{user}-{len(self.acquired)}"
        state = {"cookies": [{"name": "account_session", "value": identity,
                  "domain": "127.0.0.1", "path": "/", "expires": -1,
                  "httpOnly": True, "secure": False, "sameSite": "Lax"}],
                 "origins": [{"origin": self.origin, "localStorage": [
                     {"name": "account_session", "value": identity}]}]}
        return ports.UserSession(principal_id="principal-" + user,
            authentication_id=identity, credentials=SimpleNamespace(context={
                "storage_state": state, "extra_http_headers": {"Authorization": "Bearer " + identity}}))


class ObservedUi(SyntheticUi):
    def __init__(self, origin, *, fault=None):
        super().__init__(origin)
        self.opened, self.closed, self.observed = [], [], []
        self.permits, self.sessions = [], []
        self.fault = fault

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None, **identity):
        options = getattr(session, "context", None)
        if self.fault == "inherit_credentials" and identity["user"] is None:
            options = self.sessions[0].context
        context = self.support.open(mode, mock_plan=mock_plan,
                                    context_options=options, **identity)
        self.opened.append(context)
        self.sessions.append(session)
        return context

    def perform_step(self, scenario, step, context, permit):
        self.permits.append(permit)
        if step.id == "access/reader_send":
            if self.fault == "wrong_user":
                permit = dataclasses.replace(permit, user="owner")
            elif self.fault == "wrong_generation":
                permit = dataclasses.replace(permit, session_generation=True)
            elif self.fault == "wrong_context_id":
                permit = dataclasses.replace(permit, context_id=self.opened[0].context_id)
            elif self.fault == "wrong_context":
                context = self.opened[0]
            elif self.fault == "replayed_permit":
                permit = self.permits[2]
        outcome = super().perform_step(scenario, step, context, permit)
        self.observed.append({"step": step.id, "context": context, "permit": permit,
            "storage": context.page.evaluate("localStorage.getItem('account_session')"),
            "cookies": context.browser_context.cookies(), "outcome": outcome})
        if step.id == "access/reader_send":
            if self.fault == "stale_evidence":
                return self.observed[2]["outcome"]
            if self.fault == "wrong_evidence_user":
                return dataclasses.replace(outcome, evidence=dataclasses.replace(outcome.evidence, user="owner"))
        return outcome

    def close_stepwise(self, context):
        assert not any(old is context for old in self.closed)
        self.closed.append(context)
        super().close_stepwise(context)
        if self.fault == "close_failure" and context.user is None:
            raise ValueError("synthetic anonymous cleanup failure")


def interaction(user, label):
    return [
        {"id": user + "_open", "user": user, "do": "open", "target": "laboratory"},
        {"id": user + "_fill", "user": user, "do": "fill", "target": "value", "value": label},
        send(user + "_send", user, label),
    ]


def send(sid, user, label):
    return {"id": sid, "user": user, "do": "click", "target": "fetch",
            "expect": {"request": {"method": "POST", "path": ["api", "echo"], "body": {"value": label}},
                       "response": [{"check": "status_equals", "value": 200},
                                    {"check": "field_equals", "field": "reply", "value": label}]}}


def included(tmp_path, *, reader="anonymous"):
    child = {"schema_version": 1, "scenario": "shared.browser_access", "users": ["creator", "reader"],
             "steps": interaction("creator", "owner value") + interaction("reader", "reader value")}
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(child, sort_keys=False))
    root = {"schema_version": 1, "scenario": "browser.mixed_access", "users": ["owner", reader],
            "steps": [{"id": "access", "do": {"include": child["scenario"]},
                       "with_users": {"creator": "owner", "reader": reader}},
                      send("owner_return", "owner", "owner value"),
                      send("reader_return", reader, "reader value")]}
    path = tmp_path / "parent.yaml"
    path.write_text(yaml.safe_dump(root, sort_keys=False))
    path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
        "scenarios": {child["scenario"]: {"path": "child.yaml",
            "sha256": hashlib.sha256(child_path.read_bytes()).hexdigest()}}}))
    return path, child_path


def execute(path, ui, auth, projection):
    adapters = Adapters(auth, None, None, ui, InMemoryRecorder, None, FakeNormalizer())
    plan = [fixture("named-first", reply="owner value"), fixture("reader-first", reply="reader value"),
            fixture("named-return", reply="owner value"), fixture("reader-return", reply="reader value")]
    return run_scenario(path, adapters, projections=(projection,),
                        mock_plan=plan if projection == "frontend" else None)


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
@pytest.mark.parametrize("reader", ["anonymous", "peer"])
def test_loaded_multiuser_include_preserves_real_contexts_and_global_mock_order(http_peer, tmp_path, projection, reader):
    path, child = included(tmp_path, reader=reader)
    frozen = child.read_bytes()
    ui, auth = ObservedUi(http_peer.base_url), Accounts(http_peer.base_url)
    report = execute(path, ui, auth, projection)
    assert report.status == "PASSED", [(s.step_id, s.status, s.detail) for s in report.domains[0].steps]
    assert report.degradations() == []
    assert child.read_bytes() == frozen
    assert auth.identified == auth.acquired == (["owner"] if reader == "anonymous" else ["owner", "peer"])
    assert len(ui.opened) == len(ui.closed) == 2
    assert all(context.closed and context.page.is_closed() for context in ui.closed)
    assert ui.observed[0]["context"] is ui.observed[6]["context"]
    assert ui.observed[3]["context"] is ui.observed[7]["context"]
    assert ui.opened[0] is not ui.opened[1]
    expected_users = ["owner"] * 3 + [None if reader == "anonymous" else reader] * 3 + ["owner", None if reader == "anonymous" else reader]
    assert [step.user for step in report.domains[0].steps] == expected_users
    assert [step.session_generation for step in report.domains[0].steps] == [0 if user is None else 1 for user in expected_users]
    for observation, user in zip(ui.observed, expected_users):
        if user is None:
            assert observation["storage"] is None and observation["cookies"] == []
        else:
            assert SECRET in observation["storage"]
            assert [cookie["value"] for cookie in observation["cookies"]] == [observation["storage"]]
    assert all(SECRET not in repr(item) for item in [report, *ui.permits, *ui.results, *ui.opened])
    if projection == "frontend":
        assert http_peer.api_requests == []
        assert len({id(context.mock_queue) for context in ui.opened}) == 1
        assert [item["fixture_id"] for item in report.domains[0].mock_consumption] == [
            "named-first", "reader-first", "named-return", "reader-return"]
    else:
        assert len(http_peer.api_requests) == 4
        assert [(r.user, r.session_generation) for r in report.domains[0].provider_recordings] == [
            (user, 0 if user is None else 1) for user in ["owner", expected_users[3], "owner", expected_users[3]]]
        for index, request in enumerate(http_peer.api_requests):
            headers = {k.lower(): v for k, v in request["headers"].items()}
            if reader == "anonymous" and index in (1, 3):
                assert "authorization" not in headers and "cookie" not in headers
            else:
                assert SECRET in headers["authorization"] and SECRET in headers["cookie"]
    # There is no implicit authentication or logout navigation in either mode.
    assert all(request["path"] in {"/", "/static/ready.js", "/favicon.ico", "/api/echo"}
               for request in http_peer.requests)


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_next_run_uses_fresh_named_and_anonymous_contexts(http_peer, tmp_path, projection):
    path, _ = included(tmp_path)
    ui, auth = ObservedUi(http_peer.base_url), Accounts(http_peer.base_url)
    assert execute(path, ui, auth, projection).status == "PASSED"
    assert execute(path, ui, auth, projection).status == "PASSED"
    assert len(ui.opened) == len(ui.closed) == 4
    assert len({id(context) for context in ui.opened}) == len({context.context_id for context in ui.opened}) == 4
    assert auth.acquired == ["owner", "owner"]
    assert ui.observed[0]["storage"] != ui.observed[8]["storage"]
    assert ui.observed[3]["storage"] is ui.observed[11]["storage"] is None
    assert ui.observed[0]["permit"].execution_id != ui.observed[8]["permit"].execution_id


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
@pytest.mark.parametrize("fault", ["wrong_user", "wrong_generation", "wrong_context_id", "wrong_context",
                                  "replayed_permit", "stale_evidence", "wrong_evidence_user", "inherit_credentials"])
def test_mixed_context_faults_cannot_pass_and_every_open_context_closes(http_peer, tmp_path, projection, fault):
    path, _ = included(tmp_path)
    ui = ObservedUi(http_peer.base_url, fault=fault)
    report = execute(path, ui, Accounts(http_peer.base_url), projection)
    domain = report.domains[0]
    assert report.status != "PASSED"
    failed = 3 if fault == "inherit_credentials" else 5
    assert domain.steps[failed].status == "ERROR", [(s.step_id, s.status, s.detail) for s in domain.steps]
    assert all(step.status == "BLOCKED" for step in domain.steps[failed + 1:])
    assert len(ui.opened) == len(ui.closed) == (1 if fault == "inherit_credentials" else 2)
    assert all(context.closed and context.page.is_closed() for context in ui.closed)
    assert SECRET not in repr(report)
    if projection == "e2e":
        assert len(http_peer.api_requests) == (2 if fault in {"stale_evidence", "wrong_evidence_user"} else 1)
    else:
        assert http_peer.api_requests == []


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_anonymous_close_failure_is_visible_and_named_context_also_closes(http_peer, tmp_path, projection):
    path, _ = included(tmp_path)
    ui = ObservedUi(http_peer.base_url, fault="close_failure")
    report = execute(path, ui, Accounts(http_peer.base_url), projection)
    assert report.status != "PASSED" and report.domains[0].steps[-1].status == "ERROR"
    assert len(ui.opened) == len(ui.closed) == 2
    assert all(context.page.is_closed() for context in ui.closed)


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_explicit_anonymous_only_needs_no_authenticator(http_peer, tmp_path, projection):
    raw = {"schema_version": 1, "scenario": "browser.anonymous_only", "users": ["anonymous"],
           "steps": interaction("anonymous", "owner value")}
    for step in raw["steps"]:
        del step["user"]
    path = tmp_path / "anonymous.yaml"
    path.write_text(yaml.safe_dump(raw))
    ui = ObservedUi(http_peer.base_url)
    report = execute(path, ui, None, projection)
    assert report.status == "PASSED", [(s.status, s.detail) for s in report.domains[0].steps]
    assert ui.sessions == [None]
    assert len(ui.closed) == 1
    assert all(row["storage"] is None and row["cookies"] == [] for row in ui.observed)
    assert all((step.user, step.session_generation) == (None, 0) for step in report.domains[0].steps)


def test_flattened_and_included_real_requests_are_equivalent(http_peer, tmp_path):
    path, _ = included(tmp_path)
    included_report = execute(path, ObservedUi(http_peer.base_url), Accounts(http_peer.base_url), "e2e")
    assert included_report.status == "PASSED"
    loaded = load_scenario(path)
    # Hand-authored equivalent declaration, not a second runtime expansion loop.
    raw = {"schema_version": 1, "scenario": "browser.flat_mixed", "users": ["owner", "anonymous"],
           "steps": interaction("owner", "owner value") + interaction("anonymous", "reader value") + [
               send("owner_return", "owner", "owner value"), send("reader_return", "anonymous", "reader value")]}
    flat_path = tmp_path / "flat.yaml"
    flat_path.write_text(yaml.safe_dump(raw))
    flat_report = execute(flat_path, ObservedUi(http_peer.base_url), Accounts(http_peer.base_url), "e2e")
    assert flat_report.status == "PASSED"
    assert len(loaded.steps) == len(raw["steps"]) == 8
    def observations(report):
        return [(r.user, r.session_generation, r.status, r.request.method, r.request.path, r.request.body, r.json)
                for r in report.domains[0].provider_recordings]
    assert observations(included_report) == observations(flat_report)
    assert len(http_peer.api_requests) == 8
