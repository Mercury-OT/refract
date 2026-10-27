"""User/session isolation in the one shared mock and live UI execution loop."""
import dataclasses

import pytest

from refracto import ports
from refracto.declaration.model import Assertion, Binding, Expect, PollPolicy, RequestTemplate, Step, ValueRef
from refracto.report import RunReport
from refracto.runner import PollConfig
from tests.fakes import FakeApi, FakeAuth
from tests.ui_support import ScriptedUi, response, run, scenario


class CountingAuth(FakeAuth):
    def __init__(self):
        self.identified = []
        self.acquired = []

    def identify(self, user):
        self.identified.append(user)
        return "principal-" + user

    def session(self, user):
        self.acquired.append(user)
        return ports.UserSession(principal_id="principal-" + user,
            authentication_id=f"authentication-{len(self.acquired)}",
            credentials={"user": user, "credential": f"sensitive-{len(self.acquired)}"})


class TrackingUi(ScriptedUi):
    def __init__(self, *args, fail_open=None, fail_close=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.opened, self.closed, self.used = [], [], []
        self.fail_open, self.fail_close = fail_open, fail_close

    def open_stepwise(self, *args, **kwargs):
        if self.fail_open is not None and kwargs["user"] == self.fail_open:
            raise ValueError("context unavailable")
        context = super().open_stepwise(*args, **kwargs)
        self.opened.append(context)
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        assert all(context[key] == getattr(permit, key)
                   for key in ("user", "session_generation", "context_id"))
        self.used.append(context)
        return super().perform_step(context, permit, business_header_names=business_header_names)

    def close_stepwise(self, context):
        assert not any(existing is context for existing in self.closed)
        self.closed.append(context)
        super().close_stepwise(context)
        if self.fail_close is not None and context["user"] == self.fail_close:
            raise ValueError("context cleanup unavailable")


def multiple(users=("creator", "peer", "creator", "creator", "peer")):
    declaration = scenario(count=len(users))
    declaration.users = list(dict.fromkeys(users))
    for step, user in zip(declaration.steps, users):
        step.user = user
    return declaration


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_switching_reuses_selected_context_new_replaces_only_selected_and_global_mocks(mode):
    declaration = multiple()
    declaration.steps[3].session = "new"
    ui, auth = TrackingUi(count=5), CountingAuth()
    result = run(declaration, ui, auth=auth, mode=mode)
    assert [step.status for step in result.steps] == ["PASSED"] * 5
    assert auth.identified == ["creator", "peer"]
    assert auth.acquired == ["creator", "peer", "creator"]
    assert [step.session_generation for step in result.steps] == [1, 1, 1, 2, 1]
    assert ui.used[0] is ui.used[2] and ui.used[1] is ui.used[4]
    assert ui.used[3] is not ui.used[0]
    assert len(ui.opened) == len(ui.closed) == 3
    assert len({permit.context_id for permit in ui.permits}) == 3
    if mode == "mock":
        assert [item["fixture_id"] for item in result.mock_consumption] == [f"f{i}-0" for i in range(5)]
        assert len({id(context["mock_queue"]) for context in ui.opened}) == 1
    else:
        assert [(r.user, r.session_generation) for r in result.provider_recordings] == [
            ("creator", 1), ("peer", 1), ("creator", 1), ("creator", 2), ("peer", 1)]
    assert "sensitive-" not in repr(RunReport("synthetic", [result]))


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("layer,field,value", [
    ("evidence", "user", "other"), ("evidence", "session_generation", True),
    ("evidence", "context_id", "other-context"), ("traffic", "user", "other"),
    ("traffic", "session_generation", 0), ("traffic", "context_id", "other-context"),
    ("response", "user", "other"), ("response", "session_generation", False),
])
def test_cross_user_context_and_stale_generation_cannot_satisfy_checks(mode, layer, field, value):
    def mutate(index, outcome, permit):
        evidence = outcome.evidence
        if layer == "evidence":
            evidence = dataclasses.replace(evidence, **{field: value})
        else:
            traffic = evidence.traffic[0]
            if layer == "response":
                traffic = dataclasses.replace(traffic, response=dataclasses.replace(traffic.response, **{field: value}))
            else:
                traffic = dataclasses.replace(traffic, **{field: value})
            evidence = dataclasses.replace(evidence, traffic=[traffic])
        return dataclasses.replace(outcome, evidence=evidence)
    ui = TrackingUi(mutate=mutate)
    result = run(multiple(("creator", "peer")), ui, mode=mode)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert len(ui.opened) == len(ui.closed) == 1


def test_preflight_duplicate_accounts_has_zero_contexts_actions_or_authentication():
    class Duplicate(CountingAuth):
        def identify(self, user):
            return "same-principal"
    auth, ui = Duplicate(), TrackingUi()
    result = run(multiple(("creator", "peer")), ui, auth=auth)
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert ui.opened == ui.permits == auth.acquired == []


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_anonymous_execution_never_calls_authenticator(mode):
    class Forbidden(FakeAuth):
        def identify(self, user):
            pytest.fail("anonymous identified an account")
        def session(self, user):
            pytest.fail("anonymous authenticated")
    declaration = scenario()
    declaration.users = []
    ui = TrackingUi(fail_open="never")
    result = run(declaration, ui, auth=Forbidden(), mode=mode)
    assert [step.status for step in result.steps] == ["PASSED", "PASSED"]
    assert [(step.user, step.session_generation) for step in result.steps] == [(None, 0)] * 2
    assert ui.opened[0]["session"] is None


def test_dependency_blocked_new_session_does_not_replace_or_authenticate():
    declaration = multiple(("creator", "creator", "creator"))
    declaration.steps[1].session = "new"
    declaration.steps[1].bind = [Binding("missing", "s0", "id")]
    declaration.steps[1].value = ValueRef("bind", "missing")
    ui, auth = TrackingUi(payloads=[response({"name": "alpha"}), response()]), CountingAuth()
    result = run(declaration, ui, auth=auth)
    assert [step.status for step in result.steps] == ["FAILED", "BLOCKED", "PASSED"]
    assert auth.acquired == ["creator"]
    assert [step.session_generation for step in result.steps] == [1, None, 1]
    assert ui.used[0] is ui.used[1]


def test_cross_user_response_reference_reports_source_user_and_generation():
    declaration = multiple(("creator", "peer"))
    declaration.steps[1].bind = [Binding("owner_id", "s0", "id")]
    declaration.steps[1].value = ValueRef("bind", "owner_id")
    result = run(declaration, TrackingUi())
    origin = result.steps[1].binding_sources["owner_id"].origin
    assert (origin.user, origin.session_generation) == ("creator", 1)
    assert (result.steps[1].user, result.steps[1].session_generation) == ("peer", 1)


def test_api_new_session_closes_old_ui_and_next_ui_uses_same_new_credentials():
    declaration = multiple(("creator", "creator", "creator"))
    declaration.steps[1] = Step("api", RequestTemplate("GET", "items"),
        Expect(response=[Assertion("success")]), user="creator", session="new")
    class InspectApi(FakeApi):
        def send(self, request, session):
            self.session_used = session
            return super().send(request, session)
    api, auth, ui = InspectApi(), CountingAuth(), TrackingUi()
    result = run(declaration, ui, auth=auth, api=api,
        resolve_request=lambda template: ports.RequestSpec(template.method, template.path, template.body))
    assert [step.status for step in result.steps] == ["PASSED"] * 3
    assert auth.acquired == ["creator", "creator"]
    assert ui.opened[1]["session"] is api.session_used
    assert len(ui.opened) == len(ui.closed) == 2
    assert [(r.user, r.session_generation) for r in result.provider_recordings] == [("creator", 1), ("creator", 2), ("creator", 2)]


@pytest.mark.parametrize("failure", ["open", "action", "close"])
def test_all_opened_user_contexts_closed_once_even_when_one_operation_fails(failure):
    ui = TrackingUi(fail_open="peer" if failure == "open" else None,
                    fail_close="creator" if failure == "close" else None,
                    terminal=(1, "error") if failure == "action" else None)
    result = run(multiple(("creator", "peer")), ui)
    assert "ERROR" in [step.status for step in result.steps]
    assert len(ui.closed) == len(ui.opened) == (1 if failure == "open" else 2)


@pytest.mark.parametrize("mismatch", ["principal", "authentication"])
def test_new_authentication_mismatch_stops_without_new_context_or_action(mismatch):
    class InvalidNew(CountingAuth):
        def session(self, user):
            value = super().session(user)
            if len(self.acquired) == 2:
                return dataclasses.replace(value, **({"principal_id": "another-account"}
                    if mismatch == "principal" else {"authentication_id": "authentication-1"}))
            return value
    declaration = multiple(("creator", "creator", "creator"))
    declaration.steps[1].session = "new"
    ui = TrackingUi(count=3)
    result = run(declaration, ui, auth=InvalidNew())
    assert [step.status for step in result.steps] == ["PASSED", "ERROR", "BLOCKED"]
    assert len(ui.permits) == len(ui.opened) == len(ui.closed) == 1
    assert [step.session_generation for step in result.steps] == [1, None, None]


def test_adapter_cannot_change_signed_permit_user_binding():
    class MutatedPermit(ScriptedUi):
        def perform_step(self, context, permit, *, business_header_names=()):
            object.__setattr__(permit, "user", "peer")
            return super().perform_step(context, permit, business_header_names=business_header_names)
    result = run(multiple(("creator", "peer")), MutatedPermit())
    assert [step.status for step in result.steps] == ["ERROR", "BLOCKED"]
    assert "permit was modified" in result.steps[0].detail


def test_live_api_polling_reuses_current_session_without_any_browser_context():
    declaration = multiple(("creator",))
    declaration.steps = [Step("ready", RequestTemplate("GET", "items"),
        Expect(response=[Assertion("success")]), poll=PollPolicy("FAIL"), user="creator")]
    class PollApi(FakeApi):
        def __init__(self):
            super().__init__()
            self.sessions = []
        def send(self, request, session):
            self.sessions.append(session)
            result = super().send(request, session)
            result.json["success"] = len(self.sessions) >= 2
            return result
    api, auth, ui = PollApi(), CountingAuth(), TrackingUi(count=1)
    clock = [0]
    result = run(declaration, ui, auth=auth, api=api,
        resolve_request=lambda template: ports.RequestSpec(template.method, template.path, template.body),
        poll_config=PollConfig(timeout=3, interval=1), now=lambda: clock[0],
        sleep=lambda duration: clock.__setitem__(0, clock[0] + duration))
    assert result.steps[0].status == "PASSED"
    assert auth.acquired == ["creator"] and api.sessions[0] is api.sessions[1]
    assert ui.opened == ui.closed == []
    assert [(record.user, record.session_generation) for record in result.provider_recordings] == [("creator", 1)] * 2
