"""Shared-loop controls for the anonymous runtime identity in mixed users."""
import dataclasses

import pytest

from refracto.declaration.model import Assertion, Binding, Expect, Step, ValueRef
from refracto.report import RunReport
from tests.test_ui_users_sessions import CountingAuth, TrackingUi, multiple
from tests.ui_support import run


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_named_anonymous_named_reuses_only_its_own_context(mode):
    declaration = multiple(("owner", "anonymous", "owner", "anonymous"))
    ui, auth = TrackingUi(count=4), CountingAuth()
    result = run(declaration, ui, auth=auth, mode=mode)
    assert [step.status for step in result.steps] == ["PASSED"] * 4
    assert auth.identified == auth.acquired == ["owner"]
    assert [(s.user, s.session_generation) for s in result.steps] == [("owner", 1), (None, 0), ("owner", 1), (None, 0)]
    assert ui.used[0] is ui.used[2] and ui.used[1] is ui.used[3]
    assert ui.used[0] is not ui.used[1]
    assert ui.used[1]["session"] is None
    assert len(ui.opened) == len(ui.closed) == 2
    assert "sensitive-" not in repr(RunReport(declaration.id, [result]))
    if mode == "mock":
        assert len({id(context["mock_queue"]) for context in ui.opened}) == 1
        assert [item["fixture_id"] for item in result.mock_consumption] == [f"f{i}-0" for i in range(4)]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_named_renewal_leaves_current_anonymous_context_unchanged(mode):
    declaration = multiple(("owner", "anonymous", "owner", "anonymous", "owner"))
    declaration.steps[2].session = "new"
    ui, auth = TrackingUi(count=5), CountingAuth()
    result = run(declaration, ui, auth=auth, mode=mode)
    assert [s.status for s in result.steps] == ["PASSED"] * 5
    assert auth.acquired == ["owner", "owner"]
    assert [s.session_generation for s in result.steps] == [1, 0, 2, 0, 2]
    assert ui.used[0] is not ui.used[2] and ui.used[2] is ui.used[4]
    assert ui.used[1] is ui.used[3]
    assert len(ui.closed) == len(ui.opened) == 3


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("layer,field,value", [
    ("evidence", "user", "anonymous"), ("evidence", "user", "owner"),
    ("evidence", "session_generation", False), ("evidence", "session_generation", 1),
    ("evidence", "context_id", "named-context"),
    ("traffic", "user", "owner"), ("traffic", "session_generation", True),
    ("response", "user", "owner"), ("response", "session_generation", False),
])
def test_anonymous_evidence_cannot_claim_named_or_mistyped_identity(mode, layer, field, value):
    def mutate(index, outcome, permit):
        if index != 1:
            return outcome
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
    ui, auth = TrackingUi(count=3, mutate=mutate), CountingAuth()
    result = run(multiple(("owner", "anonymous", "owner")), ui, auth=auth, mode=mode)
    assert [s.status for s in result.steps] == ["PASSED", "ERROR", "BLOCKED"]
    assert len(ui.permits) == 2
    assert len(ui.opened) == len(ui.closed) == 2
    assert auth.acquired == ["owner"]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_reference_from_anonymous_response_reports_no_account_and_generation_zero(mode):
    declaration = multiple(("anonymous", "owner"))
    declaration.steps[1].bind = [Binding("previous", "s0", "id")]
    declaration.steps[1].value = ValueRef("bind", "previous")
    result = run(declaration, TrackingUi(), auth=CountingAuth(), mode=mode)
    assert [s.status for s in result.steps] == ["PASSED", "PASSED"]
    origin = result.steps[1].binding_sources["previous"].origin
    assert (origin.user, origin.session_generation) == (None, 0)
    assert (result.steps[1].user, result.steps[1].session_generation) == ("owner", 1)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_anonymous_wait_observation_uses_separate_context_without_login(mode):
    declaration = multiple(("owner", "anonymous", "owner"))
    declaration.steps[1] = Step("observe", None,
        Expect(frontend=[Assertion("visible", {"anchor": "rows"})]),
        action="wait", duration=0, user="anonymous")
    ui, auth = TrackingUi(), CountingAuth()
    result = run(declaration, ui, auth=auth, mode=mode)
    assert [s.status for s in result.steps] == ["PASSED"] * 3
    assert auth.acquired == ["owner"]
    assert len(ui.opened) == len(ui.closed) == 2
    assert ui.opened[1]["session"] is None and ui.opened[1]["user"] is None
    assert ui.used[0] is ui.used[1]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_programmatic_anonymous_reauthentication_fails_before_any_context_or_account(mode):
    declaration = multiple(("owner", "anonymous"))
    declaration.steps[1].session = "new"
    ui, auth = TrackingUi(), CountingAuth()
    result = run(declaration, ui, auth=auth, mode=mode)
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert ui.opened == ui.permits == auth.identified == auth.acquired == []
