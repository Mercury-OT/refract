"""Narrow operation inputs through actual Chromium, independent of checks."""
import copy
from dataclasses import asdict

import pytest
import yaml

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from tests.browser.adapter import SyntheticUi
from tests.browser.test_support import browser_lab
from tests.fakes import FakeNormalizer


FIRST = "earlier-observation-only-in-later-check-749"
SECOND = "current-primitive-input-532"
HIDDEN = "expectation-only-never-an-operation-input-891"
UNUSED = "unused-parameter-must-not-cross-port-417"


class BoundaryUi(SyntheticUi):
    def __init__(self, base_url, *, corrupt_fixture=False):
        super().__init__(base_url)
        self.open_arguments = []
        self.operation_arguments = []
        self.corrupt_fixture = corrupt_fixture

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        self.open_arguments.append({"session": session, "mode": mode,
            "mock_plan": copy.deepcopy(mock_plan), "user": user,
            "session_generation": session_generation, "context_id": context_id})
        if self.corrupt_fixture:
            mock_queue.plan[0].response["data"]["reply"] = "forged-fixture-result"
        return super().open_stepwise(session, mode=mode, mock_plan=mock_plan,
            mock_queue=mock_queue, user=user, session_generation=session_generation,
            context_id=context_id)

    def perform_step(self, context, permit, *, business_header_names=()):
        self.operation_arguments.append((asdict(permit), business_header_names))
        return super().perform_step(context, permit,
                                    business_header_names=business_header_names)


def declaration(path, *, expected=SECOND):
    document = {"schema_version": 1, "scenario": "synthetic.operation_boundary",
        "users": [], "parameters": {"hidden": HIDDEN, "unused": UNUSED}, "steps": [
            {"id": "open", "do": "open", "target": "laboratory"},
            {"id": "first_input", "do": "fill", "target": "value", "value": FIRST},
            {"id": "first", "do": "click", "target": "fetch", "expect": {
                "request": {"method": "POST", "path": ["api", "echo"], "body": {"value": FIRST}},
                "response": [{"check": "success"}, {"check": "has", "field": "reply"}]}},
            {"id": "next_input", "do": "fill", "target": "value", "value": SECOND},
            {"id": "next", "do": "click", "target": "fetch", "expect": {
                "request": {"method": "POST", "path": ["api", "echo"], "body": {"value": SECOND}},
                "ui": [{"check": "objects_matching_count", "anchor": "laboratory",
                        "count": 1, "field": "value", "value": expected}],
                "response": [
                    {"check": "field_not_equals", "field": "reply",
                     "value": {"from_step": "first", "response_field": "reply"}},
                    {"check": "field_not_equals", "field": "path", "value": {"from_parameter": "hidden"}},
                    {"check": "field_equals", "field": "reply", "value": expected}]}}
        ]}
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def plan():
    return [ports.MockResponse(fixture_id=f"explicit-{index}",
        source="independent synthetic echo fixture", method="POST", path="api/echo",
        response={"success": True, "data": {"reply": value, "path": "/api/echo"}})
        for index, value in enumerate((FIRST, SECOND))]


def run(path, ui, mode, fixtures=None):
    return run_scenario(path, Adapters(None, None, None, ui, InMemoryRecorder,
                       None, FakeNormalizer()),
                       projections=("frontend" if mode == "mock" else "e2e",),
                       mock_plan=fixtures if mode == "mock" else None)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_real_browser_operations_do_not_receive_expectations_or_assertion_only_bindings(http_peer, tmp_path, mode):
    ui = BoundaryUi(http_peer.base_url)
    report = run(declaration(tmp_path / "boundary.yaml"), ui, mode, plan())
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert len(ui.open_arguments) == 1
    assert ui.open_arguments[0]["session"] is None
    assert HIDDEN not in repr(ui.open_arguments) and UNUSED not in repr(ui.open_arguments)
    assert len(ui.operation_arguments) == 5
    for values, names in ui.operation_arguments:
        assert "resolved_bindings" not in values
        assert "scenario" not in values and "step" not in values and "expect" not in values
        assert HIDDEN not in repr(values) and UNUSED not in repr(values)
        assert type(names) is tuple and names == ()
    # FIRST is a legitimate input to its fill, but only a comparison source later.
    assert ui.operation_arguments[1][0]["value"] == FIRST
    assert ui.operation_arguments[3][0]["value"] == SECOND
    assert FIRST not in repr(ui.operation_arguments[-1])
    last = report.domains[0].steps[-1]
    assert FIRST in last.resolved_bindings.values()
    assert last.binding_sources
    assert all(check.ok for check in last.checks)
    assert FIRST not in repr(report) and HIDDEN not in repr(report)
    assert len(http_peer.api_requests) == (2 if mode == "live" else 0)
    assert ui.close_calls == 1


def visible_operation_content(ui):
    ignored = {"execution_id", "action_id", "token", "context_id"}
    return [({key: value for key, value in arguments.items() if key not in ignored}, names)
            for arguments, names in ui.operation_arguments]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_changed_expectations_do_not_change_corresponding_browser_action_inputs(http_peer, tmp_path, mode):
    first, second = BoundaryUi(http_peer.base_url), BoundaryUi(http_peer.base_url)
    valid = run(declaration(tmp_path / "correct.yaml"), first, mode, plan())
    wrong = run(declaration(tmp_path / "different.yaml", expected="different-review-only-value"),
                second, mode, plan())
    assert valid.status == "PASSED", valid.localize()
    assert wrong.status == "FAILED", wrong.localize()
    assert wrong.domains[0].steps[-1].status == "FAILED"
    assert visible_operation_content(first) == visible_operation_content(second)
    assert len(http_peer.api_requests) == (4 if mode == "live" else 0)


def test_changed_shared_mock_fixture_cannot_rewrite_the_retained_plan(http_peer, tmp_path):
    fixtures = plan()
    original = copy.deepcopy(fixtures)
    ui = BoundaryUi(http_peer.base_url, corrupt_fixture=True)
    report = run(declaration(tmp_path / "mutated.yaml"), ui, "mock", fixtures)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == [
        "COMPLETED", "COMPLETED", "ERROR", "BLOCKED", "BLOCKED"]
    assert fixtures == original
    assert not http_peer.api_requests
    assert ui.close_calls == 1


def test_browser_header_collision_guard_accepts_names_only(browser_lab, http_peer):
    support, context = browser_lab(options={"extra_http_headers": {"X-Account": "credential-only"}})
    initial = list(http_peer.api_requests)
    for names in ([], {}, "x-a", ("X-A",), ("x-b", "x-a"), ("x-a", "x-a"),
                  ("authorization",), ("",)):
        with pytest.raises(ValueError):
            support.validate_request_header_names(context, names)
    with pytest.raises(ValueError, match="collide"):
        support.validate_request_header_names(context, ("x-account",))
    support.validate_request_header_names(context, ())
    support.validate_request_header_names(context, ("x-a", "x-b"))
    assert http_peer.api_requests == initial
    assert not hasattr(support, "validate_request_headers")
