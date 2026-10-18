"""Bounded member references using real Chromium traffic and the YAML loader.

Page payloads and mock fixtures are independent observations. Neither the page
nor the adapter reads the Scenario's assertions or its selection predicates.
"""
import copy

import pytest
import yaml

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.projection import e2e, frontend
from refracto.recorder import InMemoryRecorder
from refracto.report import RunReport
from tests.browser.adapter import SyntheticUi, fields
from tests.fakes import FakeAuth, FakeNormalizer


SECRET = "synthetic-member-reference-sentinel-471"


class MemberUi(SyntheticUi):
    """Install fixture-owned page behavior without interpreting expectations."""

    def __init__(self, base_url, payload, after, *, use_path):
        super().__init__(base_url)
        self.configuration = copy.deepcopy({
            "payload": payload, "after": after, "usePath": use_path,
        })

    def perform_step(self, scenario, step, context, permit):
        result = super().perform_step(scenario, step, context, permit)
        if step.action == "open":
            context.page.evaluate("""configuration => {
                const send = (path, value) => fetch(path, {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({value})
                }).then(response => response.json()).then(body => {
                    document.querySelector('#result').textContent = JSON.stringify(body);
                });
                for (const id of ['member-source', 'member-consumer']) {
                    const button = document.createElement('button');
                    button.id = id;
                    button.textContent = id;
                    document.body.appendChild(button);
                }
                document.querySelector('#member-source').addEventListener('click', () =>
                    send('/api/member-source', configuration.payload));
                document.querySelector('#member-consumer').addEventListener('click', () =>
                    send(configuration.usePath
                        ? '/api/member/' + encodeURIComponent(configuration.after)
                        : '/api/member-result', configuration.after));
            }""", self.configuration)
        return result


def reference(kind, *, predicate="B", field="id"):
    result = {"from_step": "source", "response_field": "reply"}
    if kind == "dictionary":
        result["key"] = field
    else:
        result.update(matching={"code": predicate}, member_field=field)
    return result


def declaration(tmp_path, payload, selected, after, *, use_path=True, fill=False):
    steps = [
        {"id": "open", "do": "open", "target": "laboratory"},
        {"id": "source", "do": "click", "target": "member-source", "expect": {
            "request": {"method": "POST", "path": ["api", "member-source"],
                        "body": {"value": payload}},
            "response": [{"check": "status_equals", "value": 200},
                         {"check": "success"}],
        }},
    ]
    if fill:
        steps.append({"id": "fill", "do": "fill", "target": "value", "value": copy.deepcopy(selected)})
    else:
        steps.append({"id": "consumer", "do": "click", "target": "member-consumer", "expect": {
            "request": {"method": "POST", "path": (
                ["api", "member", copy.deepcopy(selected)] if use_path else ["api", "member-result"]),
                "body": {"value": after}},
            "response": [{"check": "status_equals", "value": 200}, {"check": "success"},
                         {"check": "field_equals", "field": "reply", "value": copy.deepcopy(selected)}],
        }})
    steps.append({"id": "independent", "do": "click", "target": "noop"})
    source = {"schema_version": 1, "scenario": "synthetic.member_references",
              "description": "Read actual response members before another browser action",
              "users": ["editor"], "steps": steps}
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    return load_scenario(str(path))


def run_members(http_peer, tmp_path, mode, payload, selected, after=22, *,
                use_path=True, fill=False):
    scenario = declaration(tmp_path, payload, selected, after, use_path=use_path, fill=fill)
    ui = MemberUi(http_peer.base_url, payload, after, use_path=use_path)
    common = dict(ui=ui, auth=FakeAuth(), normalizer=FakeNormalizer())
    if mode == "mock":
        plan = [ports.MockResponse(
            fixture_id="member-source", source="independent response member fixture",
            method="POST", path="api/member-source",
            response={"success": True, "data": {"reply": copy.deepcopy(payload)}},
        )]
        if not fill:
            plan.append(ports.MockResponse(
                fixture_id="member-consumer", source="independent response member fixture",
                method="POST", path=f"api/member/{after}" if use_path else "api/member-result",
                response={"success": True, "data": {"reply": copy.deepcopy(after)}},
            ))
        result = frontend.run(scenario, mock_plan=plan, **common)
    else:
        result = e2e.run(scenario, recorder=InMemoryRecorder(), state=None, **common)
    return result, ui


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("kind", ["dictionary", "list"])
@pytest.mark.parametrize("identifier", [22, 0])
def test_actual_selected_id_drives_request_path_and_response_check(http_peer, tmp_path, mode, kind, identifier):
    record = {"code": "B", "id": identifier}
    payload = record if kind == "dictionary" else [{"code": "A", "id": 91}, record]
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference(kind), identifier)
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "PASSED", "COMPLETED"]
    assert result.status == "PASSED"
    assert list(result.steps[2].resolved_bindings.values()) == [identifier]
    assert ui.actions == ["open", "click", "click", "click"]
    assert ui.close_calls == 1
    source, consumer = [outcome.evidence.traffic[0] for outcome in ui.results[1:3]]
    assert source.response.json["data"]["reply"] == payload
    assert consumer.request.path == f"api/member/{identifier}"
    assert consumer.response.json["data"]["reply"] == identifier
    if mode == "live":
        assert [item["path"] for item in http_peer.api_requests] == [
            "/api/member-source", f"/api/member/{identifier}",
        ]
        assert [record.step_id for record in result.provider_recordings] == ["source", "consumer"]
    else:
        assert http_peer.api_requests == []
        assert len(result.mock_consumption) == 2


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("kind,payload", [
    ("dictionary", []),
    ("dictionary", {"other": 22}),
    ("dictionary", {"id": None}),
    ("list", {"code": "B", "id": 22}),
    ("list", []),
    ("list", [{"code": "A", "id": 22}]),
    ("list", [{"code": "B", "id": 22}, {"code": "B", "id": 23}]),
    ("list", [{"code": "B", "id": 22}, "malformed"]),
    ("list", [{"code": "B"}]),
    ("list", [{"code": "B", "id": None}]),
], ids=["wrong-dictionary", "missing-key", "null-key", "wrong-list", "empty-list",
        "no-match", "duplicate-match", "malformed-member", "missing-member-field", "null-member-field"])
def test_unavailable_selection_blocks_before_action_and_independent_step_continues(http_peer, tmp_path, mode, kind, payload):
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference(kind))
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "BLOCKED", "COMPLETED"]
    assert result.status != "PASSED"
    assert result.steps[2].resolved_bindings == {}
    assert result.steps[2].blocked_by == ["source"]
    assert ui.actions == ["open", "click", "click"]
    assert len([outcome for outcome in ui.results if outcome.evidence.traffic]) == 1
    assert ui.close_calls == 1
    assert len(http_peer.api_requests) == (1 if mode == "live" else 0)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("kind", ["dictionary", "list"])
@pytest.mark.parametrize("value", [0, False, ""])
def test_actual_falsy_member_keeps_type_in_response_comparison(http_peer, tmp_path, mode, kind, value):
    record = {"code": "B", "id": value}
    payload = record if kind == "dictionary" else [record]
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference(kind), value, use_path=False)
    assert result.status == "PASSED"
    observed, = result.steps[2].resolved_bindings.values()
    assert type(observed) is type(value) and observed == value
    assert ui.actions == ["open", "click", "click", "click"]


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("kind", ["dictionary", "list"])
@pytest.mark.parametrize("value", [False, ""])
def test_preserved_falsy_value_is_not_coerced_into_a_request_path(http_peer, tmp_path, mode, kind, value):
    record = {"code": "B", "id": value}
    payload = record if kind == "dictionary" else [record]
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference(kind))
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "BLOCKED", "COMPLETED"]
    assert result.steps[2].resolved_bindings == {}
    assert ui.actions == ["open", "click", "click"]
    assert len(http_peer.api_requests) == (1 if mode == "live" else 0)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_list_predicate_does_not_confuse_false_with_zero(http_peer, tmp_path, mode):
    payload = [{"code": 0, "id": 91}, {"code": False, "id": 22}]
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference("list", predicate=False))
    assert result.status == "PASSED"
    assert ui.results[2].evidence.traffic[0].request.path == "api/member/22"


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("kind", ["dictionary", "list"])
def test_member_value_reaches_real_browser_fill(http_peer, tmp_path, mode, kind):
    record = {"code": "B", "id": "observed-label"}
    payload = record if kind == "dictionary" else [{"code": "A", "id": "other"}, record]
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference(kind), fill=True)
    assert result.status == "PASSED"
    assert ui.actions == ["open", "click", "fill", "click"]
    assert fields(ui.results[2].evidence.rendered)["value"] == "observed-label"
    assert list(result.steps[2].resolved_bindings.values()) == ["observed-label"]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_selected_id_cannot_relabel_a_different_actual_browser_request(http_peer, tmp_path, mode):
    result, ui = run_members(http_peer, tmp_path, mode, {"id": 22}, reference("dictionary"), 23)
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "ERROR", "BLOCKED"]
    assert result.status == "FAILED"
    assert ui.results[2].evidence.traffic[0].request.path == "api/member/23"
    assert ui.actions == ["open", "click", "click"]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_ambiguous_selection_diagnostics_do_not_disclose_observed_members(http_peer, tmp_path, mode):
    payload = [{"code": SECRET, "id": SECRET}, {"code": SECRET, "id": "other"}]
    result, ui = run_members(http_peer, tmp_path, mode, payload, reference("list", predicate=SECRET))
    assert result.steps[2].status == "BLOCKED"
    assert ui.actions == ["open", "click", "click"]
    report = RunReport("synthetic.member_references", [result])
    assert SECRET not in repr(report)
    assert SECRET not in str(report.localize())
    assert all(SECRET not in step.detail for step in result.steps)
