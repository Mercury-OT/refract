"""Real Chromium: account storage, replacement, and cross-context mock order.

The Demo does not enforce authorization. Documents tests prove actual access
policy; these tests prove browser isolation and evidence, never permissions.
"""
from types import SimpleNamespace

import pytest
import yaml

from adapters.demo.config import DemoConfig
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto import ports
from refracto.runner import run_scenario
from tests.demo.ui_fixtures import creation_plan


class BrowserAccounts(ports.Authenticator):
    def __init__(self, origin):
        self.origin, self.calls = origin, []

    def identify(self, user):
        return "browser-principal-" + user

    def session(self, user):
        self.calls.append(user)
        identity = f"{user}-{len(self.calls)}"
        state = {"cookies": [{"name": "account_session", "value": identity,
                  "domain": "127.0.0.1", "path": "/", "expires": -1,
                  "httpOnly": True, "secure": False, "sameSite": "Lax"}],
                 "origins": [{"origin": self.origin, "localStorage": [
                     {"name": "account_session", "value": identity}]}]}
        return ports.UserSession(principal_id=self.identify(user), authentication_id=identity,
            credentials=SimpleNamespace(context={"storage_state": state}))


class ObservedUi(DemoUiDriver):
    def __init__(self, config):
        super().__init__(config)
        self.opened, self.closed, self.observations = [], [], []

    def open_stepwise(self, *args, **kwargs):
        context = super().open_stepwise(*args, **kwargs)
        self.opened.append(context)
        return context

    @staticmethod
    def _read_rendered(page):
        result = DemoUiDriver._read_rendered(page)
        value = page.locator('[data-testid="item-name"]').input_value()
        result["form"] = {"identified": [{"id": "form", "fields": {"value": value}}], "anonymous": []}
        return result

    def perform_step(self, context, permit, *, business_header_names=()):
        outcome = super().perform_step(context, permit, business_header_names=business_header_names)
        self.observations.append({"step": permit.step_id, "user": permit.user,
            "generation": permit.session_generation, "context": context,
            "storage": context.page.evaluate("localStorage.getItem('account_session')"),
            "cookies": context.browser_context.cookies(), "evidence": outcome.evidence})
        return outcome

    def close_stepwise(self, context):
        assert not any(old is context for old in self.closed)
        self.closed.append(context)
        super().close_stepwise(context)


def form_expect(value):
    return {"ui": [{"check": "objects_matching_count", "anchor": "form",
                          "count": 1, "field": "value", "value": value}]}


def declaration():
    return {"schema_version": 1, "scenario": "demo.user_contexts", "users": ["creator", "peer"],
        "steps": [
            {"id": "open_creator", "user": "creator", "do": "open", "target": "items.page"},
            {"id": "reveal_creator", "user": "creator", "do": "click", "target": "items.new_button"},
            {"id": "fill_creator", "user": "creator", "do": "fill", "target": "items.name_input", "value": "old creator"},
            {"id": "open_peer", "user": "peer", "do": "open", "target": "items.page"},
            {"id": "reveal_peer", "user": "peer", "do": "click", "target": "items.new_button"},
            {"id": "fill_peer", "user": "peer", "do": "fill", "target": "items.name_input", "value": "peer value"},
            {"id": "creator_retained", "user": "creator", "do": "wait", "duration": 0, "expect": form_expect("old creator")},
            {"id": "creator_new", "user": "creator", "session": "new", "do": "open", "target": "items.page", "expect": form_expect("")},
            {"id": "peer_retained", "user": "peer", "do": "wait", "duration": 0, "expect": form_expect("peer value")},
            {"id": "reveal_new", "user": "creator", "do": "click", "target": "items.new_button"},
            {"id": "fill_new", "user": "creator", "do": "fill", "target": "items.name_input", "value": "fresh creator"},
            {"id": "create", "user": "creator", "do": "click", "target": "items.submit_button",
             "expect": {"request": {"method": "POST", "path": ["items"], "body": {"name": "fresh creator", "rows": [1, 2, 3]}},
                        "response": [{"check": "status_equals", "value": 200}, {"check": "success"},
                                     {"check": "field_equals", "field": "name", "value": "fresh creator"}]}}
        ]}


@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_real_context_switch_and_new_session_isolation(demo_server, tmp_path, projection):
    path = tmp_path / "contexts.yaml"
    path.write_text(yaml.safe_dump(declaration(), sort_keys=False))
    ui, auth = ObservedUi(DemoConfig(base_url=demo_server)), BrowserAccounts(demo_server)
    adapters = build_adapters(demo_server, ui=ui)
    adapters.auth = auth
    plan = creation_plan(("fresh creator",))
    initial = plan[0]
    plan[:1] = [ports.MockResponse(fixture_id=f"initial-{i}", source="explicit context fixture",
                method="GET", path="items", response=initial.response) for i in range(3)]
    report = run_scenario(path, adapters, projections=(projection,),
                          mock_plan=plan if projection == "frontend" else None)
    assert report.status == "PASSED", [(step.step_id, step.status, step.detail) for step in report.domains[0].steps]
    assert report.degradations() == []
    assert auth.calls == ["creator", "peer", "creator"]
    assert len(ui.opened) == len(ui.closed) == 3
    assert all(context.closed and context.page.is_closed() for context in ui.closed)
    assert ui.observations[0]["storage"] == "creator-1"
    assert ui.observations[3]["storage"] == "peer-2"
    assert next(row for row in ui.observations if row["step"] == "creator_new")["storage"] == "creator-3"
    for row in ui.observations:
        assert [cookie["value"] for cookie in row["cookies"] if cookie["name"] == "account_session"] == [row["storage"]]
        evidence = row["evidence"]
        assert (evidence.user, evidence.session_generation) == (row["user"], row["generation"])
    if projection == "frontend":
        assert [item["fixture_id"] for item in report.domains[0].mock_consumption] == [
            "initial-0", "initial-1", "initial-2", "create-1", "list-1"]
    else:
        assert [(record.user, record.session_generation) for record in report.domains[0].provider_recordings] == [("creator", 2)]


def test_real_anonymous_run_cannot_inherit_previous_account_context(demo_server, tmp_path):
    ui = ObservedUi(DemoConfig(base_url=demo_server))
    adapters = build_adapters(demo_server, ui=ui)
    adapters.auth = BrowserAccounts(demo_server)
    declaration = {"schema_version": 1, "scenario": "demo.anonymous_isolation", "users": ["creator"],
        "steps": [{"id": "open", "do": "open", "target": "items.page", "expect": form_expect("")}]}
    path = tmp_path / "anonymous.yaml"
    path.write_text(yaml.safe_dump(declaration))
    assert run_scenario(path, adapters, projections=("e2e",)).status == "PASSED"
    assert ui.observations[-1]["storage"] == "creator-1"

    class NoAuthentication:
        def identify(self, user):
            pytest.fail("anonymous run resolved an account")
        def session(self, user):
            pytest.fail("anonymous run authenticated")
    declaration["users"] = []
    path.write_text(yaml.safe_dump(declaration))
    adapters.auth = NoAuthentication()
    report = run_scenario(path, adapters, projections=("e2e",))
    assert report.status == "PASSED"
    latest = ui.observations[-1]
    assert latest["storage"] is None and latest["cookies"] == []
    assert latest["user"] is None and latest["generation"] == 0
    assert len(ui.opened) == len(ui.closed) == 2
