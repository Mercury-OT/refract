"""Numeric and actual list-length checks through real Chromium live/mock traffic.

The synthetic page owns its payloads and mock responses are explicit fixtures.
Neither reads declaration assertions to construct observed evidence.
"""
import copy

import pytest
import yaml

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.projection import e2e, frontend
from refracto.recorder import InMemoryRecorder
from refracto.report import RunReport
from tests.browser.adapter import SyntheticUi
from tests.fakes import FakeAuth, FakeNormalizer


SECRET = "synthetic-numeric-list-sentinel-587"
SECRET_ACTUAL = 7348921
SECRET_THRESHOLD = 8359032


class NumericUi(SyntheticUi):
    """Install fixture-owned actions in the existing synthetic laboratory."""

    def __init__(self, base_url, payloads):
        super().__init__(base_url)
        self.payloads = copy.deepcopy(payloads)

    def perform_step(self, scenario, step, context, permit):
        result = super().perform_step(scenario, step, context, permit)
        if step.action == "open":
            context.page.evaluate("""payloads => {
                for (const [id, value] of Object.entries(payloads)) {
                    const button = document.createElement('button');
                    button.id = 'numeric-' + id;
                    button.textContent = 'Read ' + id + ' fixture';
                    document.body.appendChild(button);
                    button.addEventListener('click', () => fetch('/api/numeric/' + id, {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value})
                    }).then(response => response.json()).then(body => {
                        document.querySelector('#result').textContent = JSON.stringify(body);
                    }));
                }
            }""", self.payloads)
        return result


class NumericNormalizer(FakeNormalizer):
    """Expose the echo peer's independently supplied record as normalized fields."""

    def normalize(self, response):
        normalized = super().normalize(response)
        normalized.fields = copy.deepcopy(normalized.fields["reply"])
        return normalized


class TrackingAuth(FakeAuth):
    def __init__(self):
        self.acquired = []

    def session(self, user):
        self.acquired.append(user)
        return super().session(user)


def constraint(check, field, op, value):
    return {"check": check, "field": field, "op": op, "value": value}


def from_source(field, **selector):
    return {"from_step": "source", "response_field": field, **selector}


def load_case(tmp_path, checks, *, source=False, source_checks=(), stop=False,
              consumer_user="editor", parameters=None):
    def action(identifier, assertions, user="editor"):
        return {"id": identifier, "do": "click", "target": "numeric-" + identifier,
                "user": user, "expect": {
                    "request": {"method": "POST", "path": ["api", "numeric", identifier]},
                    "response": [{"check": "status_equals", "value": 200},
                                 {"check": "success"}, *copy.deepcopy(assertions)],
                }}

    steps = [{"id": "open", "do": "open", "target": "laboratory", "user": "editor"}]
    if source:
        steps.append(action("source", source_checks))
        if stop:
            steps[-1]["on_failure"] = "stop"
    steps.append(action("observe", checks, consumer_user))
    steps.append({"id": "independent", "do": "click", "target": "noop", "user": "editor"})
    document = {
        "schema_version": 1, "scenario": "synthetic.response_numeric_length",
        "description": "Check observed numeric limits and actual list lengths",
        "users": ["editor"] if consumer_user == "editor" else ["editor", consumer_user],
        "parameters": parameters or {}, "steps": steps,
    }
    path = tmp_path / "numeric-length.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return load_scenario(str(path))


def run_case(http_peer, tmp_path, mode, payloads, checks, *, normalizer=None,
             mock_payloads=None, **declaration_options):
    scenario = load_case(tmp_path, checks, source="source" in payloads, **declaration_options)
    ui, auth = NumericUi(http_peer.base_url, payloads), TrackingAuth()
    common = dict(ui=ui, auth=auth, normalizer=normalizer or NumericNormalizer())
    if mode == "mock":
        observations = copy.deepcopy(payloads if mock_payloads is None else mock_payloads)
        plan = [ports.MockResponse(
            fixture_id="numeric-" + identifier,
            source="independent numeric and list-length response fixture",
            method="POST", path="api/numeric/" + identifier,
            response={"success": True, "data": {"reply": payload}},
        ) for identifier, payload in observations.items()]
        result = frontend.run(scenario, mock_plan=plan, **common)
    else:
        result = e2e.run(scenario, recorder=InMemoryRecorder(), state=None, **common)
    return result, ui, auth


def assert_traffic(http_peer, mode, result, ui, identifiers):
    traffic = [item for outcome in ui.results for item in outcome.evidence.traffic]
    assert [item.step_id for item in traffic] == identifiers
    assert [item.request.path for item in traffic] == ["api/numeric/" + name for name in identifiers]
    assert all(item.mode == ("live" if mode == "live" else "mock") for item in traffic)
    assert all(item.user == "editor" and item.session_generation == 1 for item in traffic)
    assert len({item.request_id for item in traffic}) == len(identifiers)
    assert len({item.response.trace_id for item in traffic}) == len(identifiers)
    assert all(item.response.is_final and item.response.attempt_index == 0 for item in traffic)
    assert ui.close_calls == 1
    if mode == "live":
        assert [item["path"] for item in http_peer.api_requests] == [
            "/api/numeric/" + name for name in identifiers]
        assert [record.step_id for record in result.provider_recordings] == identifiers
        assert result.mock_consumption == []
        assert all(item.mock_fixture_id is None for item in traffic)
    else:
        assert http_peer.api_requests == []
        assert result.provider_recordings == []
        assert [item["fixture_id"] for item in result.mock_consumption] == [
            "numeric-" + name for name in identifiers]
        assert [item.mock_fixture_id for item in traffic] == ["numeric-" + name for name in identifiers]
        assert "mock fixtures are not live backend evidence" in result.not_checked


def assert_safe_report(result):
    report = RunReport("synthetic.response_numeric_length", [result])
    diagnostics = [repr(report), str(report.localize()), *(step.detail for step in result.steps),
                   *(check.detail for check in result.checks)]
    assert all(value not in detail for value in (SECRET, str(SECRET_ACTUAL), str(SECRET_THRESHOLD))
               for detail in diagnostics)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("payload,checks,expected", [
    ({"returned": 1, "records": [{"id": "one"}]}, [
        constraint("field_compare", "returned", ">", 0),
        constraint("field_compare", "returned", ">=", 1),
        constraint("field_compare", "returned", "<", 1.5),
        constraint("field_compare", "returned", "<=", {"from_parameter": "page_size"}),
        constraint("collection_length", "records", ">=", 1),
        constraint("collection_length", "records", "<=", {"from_parameter": "page_size"}),
    ], [True] * 6),
    ({"returned": SECRET_ACTUAL, "records": [{"id": SECRET}]}, [
        constraint("field_compare", "returned", ">=", SECRET_THRESHOLD),
        constraint("collection_length", "records", "==", 1),
    ], [False, True]),
    ({"returned": 1, "records": [{"id": "one"}, {"id": "two"}]}, [
        constraint("field_compare", "returned", "<=", 1),
        constraint("collection_length", "records", "<=", 1),
    ], [True, False]),
    ({"returned": True}, [constraint("field_compare", "returned", "==", 1)], [False]),
    ({"returned": 1}, [constraint("field_compare", "returned", "==", 1.0)], [False]),
    ({"records": []}, [constraint("collection_length", "records", "==", 0)], [True]),
    ({"records": [None, SECRET, SECRET, {"nested": [False, 0]}, []]}, [
        constraint("collection_length", "records", "==", 5),
    ], [True]),
], ids=["all-bounds", "false-reported-count", "oversized-list", "bool-is-not-int",
        "int-is-not-float", "actual-empty-list", "duplicates-and-mixed-members"])
def test_actual_browser_numeric_and_length_checks(http_peer, tmp_path, mode, payload, checks, expected):
    original = copy.deepcopy(payload)
    result, ui, auth = run_case(http_peer, tmp_path, mode, {"observe": payload}, checks,
                                parameters={"page_size": 1})
    passed = all(expected)
    assert [step.status for step in result.steps] == [
        "COMPLETED", "PASSED" if passed else "FAILED", "COMPLETED"]
    assert result.status == ("PASSED" if passed else "FAILED")
    numeric = [item for item in result.steps[1].checks
               if item.check in {"field_compare", "collection_length"}]
    assert [item.ok for item in numeric] == expected
    assert [item.check for item in numeric] == [item["check"] for item in checks]
    for actual, declared in zip(numeric, checks):
        if not actual.ok:
            assert all(word in actual.detail for word in (declared["check"], declared["field"], declared["op"]))
    assert result.steps[-1].after_failures == ([] if passed else ["observe"])
    assert ui.actions == ["open", "click", "click"]
    assert auth.acquired == ["editor"]
    assert payload == original
    assert ui.results[1].evidence.traffic[0].response.json["data"]["reply"] == original
    assert_traffic(http_peer, mode, result, ui, ["observe"])
    assert_safe_report(result)


def test_mock_checks_use_fixture_response_instead_of_page_request_payload(http_peer, tmp_path):
    sent = {"returned": 1, "records": [{"id": "one"}]}
    observed = {"returned": SECRET_ACTUAL, "records": []}
    result, ui, _ = run_case(http_peer, tmp_path, "mock", {"observe": sent}, [
        constraint("field_compare", "returned", "<=", 1),
        constraint("collection_length", "records", ">=", 1),
    ], mock_payloads={"observe": observed})
    assert [step.status for step in result.steps] == ["COMPLETED", "FAILED", "COMPLETED"]
    assert [item.ok for item in result.steps[1].checks
            if item.check in {"field_compare", "collection_length"}] == [False, False]
    traffic, = ui.results[1].evidence.traffic
    assert traffic.request.body == {"value": sent}
    assert traffic.response.json["data"]["reply"] == observed
    assert_traffic(http_peer, "mock", result, ui, ["observe"])
    assert_safe_report(result)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("payload,check,field", [
    ({"returned": "1"}, "field_compare", "returned"),
    ({}, "field_compare", "returned"),
    ({"records": None}, "collection_length", "records"),
    ({}, "collection_length", "records"),
], ids=["numeric-string", "missing-number", "null-list", "missing-list"])
def test_wrong_type_or_missing_current_field_fails_and_continues(http_peer, tmp_path, mode, payload, check, field):
    result, ui, _ = run_case(http_peer, tmp_path, mode, {"observe": payload}, [
        constraint(check, field, ">=", 0)])
    assert [step.status for step in result.steps] == ["COMPLETED", "FAILED", "COMPLETED"]
    comparison, = [item for item in result.steps[1].checks if item.check == check]
    assert not comparison.ok
    assert ("missing" in comparison.detail) == (field not in payload)
    assert result.steps[-1].after_failures == ["observe"]
    assert ui.actions == ["open", "click", "click"]
    assert_traffic(http_peer, mode, result, ui, ["observe"])


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("check", ["field_compare", "collection_length"])
@pytest.mark.parametrize("invalid", ["non-finite", "cycle"])
def test_invalid_examined_container_is_error_even_for_permissive_bound(http_peer, tmp_path, mode, check, invalid):
    class InvalidNormalizer(NumericNormalizer):
        def normalize(self, response):
            normalized = super().normalize(response)
            broken = [SECRET, {"nested": float("inf")}]
            if invalid == "cycle":
                broken = [SECRET]
                broken.append(broken)
            normalized.fields["examined"] = broken
            return normalized

    result, ui, _ = run_case(http_peer, tmp_path, mode, {"observe": {"examined": []}}, [
        constraint(check, "examined", ">=", 0)], normalizer=InvalidNormalizer())
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert result.status == "FAILED"
    assert result.steps[-1].blocked_by == ["observe"]
    assert ui.actions == ["open", "click"]
    assert_traffic(http_peer, mode, result, ui, ["observe"])
    assert_safe_report(result)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("check,source", [
    ("field_compare", {"good": 0, "threshold": SECRET}),
    ("collection_length", {"good": 0, "threshold": 1.5}),
    ("collection_length", {"good": 0, "threshold": None}),
    ("field_compare", {"good": 0}),
], ids=["numeric-string", "fractional-length", "null-threshold", "missing-threshold"])
def test_invalid_prior_threshold_blocks_before_authentication_or_action(http_peer, tmp_path, mode, check, source):
    result, ui, auth = run_case(http_peer, tmp_path, mode, {
        "source": source, "observe": {"returned": 1, "records": [SECRET]},
    }, [constraint("field_compare", "returned", ">=", from_source("good")),
        constraint(check, "returned" if check == "field_compare" else "records",
                   "<=", from_source("threshold"))], consumer_user="reader")
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "BLOCKED", "COMPLETED"]
    blocked = result.steps[2]
    assert blocked.resolved_bindings == {}
    assert blocked.binding_sources == {}
    assert blocked.blocked_by == ["source"]
    assert blocked.session_generation is None
    assert auth.acquired == ["editor"]
    assert result.status == "DEGRADED"
    assert ui.actions == ["open", "click", "click"]
    assert_traffic(http_peer, mode, result, ui, ["source"])
    assert_safe_report(result)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_actual_prior_member_thresholds_keep_response_and_session_provenance(http_peer, tmp_path, mode):
    payloads = {
        "source": {"floor": 1, "limits": [{"name": "other", "cap": 99}, {"name": "active", "cap": 2}]},
        "observe": {"returned": 2, "records": [SECRET, SECRET]},
    }
    result, ui, auth = run_case(http_peer, tmp_path, mode, payloads, [
        constraint("field_compare", "returned", "<=", from_source(
            "limits", matching={"name": "active"}, member_field="cap")),
        constraint("collection_length", "records", ">=", from_source("floor")),
    ])
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "PASSED", "COMPLETED"]
    observed = result.steps[2]
    assert sorted(observed.resolved_bindings.values()) == [1, 2]
    assert {source.response_field for source in observed.binding_sources.values()} == {"limits", "floor"}
    assert all(source.origin == result.steps[1].response_origin for source in observed.binding_sources.values())
    assert observed.response_origin.step_id == "observe"
    assert observed.response_origin.user == "editor"
    assert observed.response_origin.session_generation == 1
    assert observed.response_origin.attempt_index == 0 and observed.response_origin.is_final
    assert auth.acquired == ["editor"]
    assert ui.actions == ["open", "click", "click", "click"]
    assert_traffic(http_peer, mode, result, ui, ["source", "observe"])
    assert_safe_report(result)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("stop", [False, True], ids=["continue", "explicit-stop"])
def test_failed_source_supplies_actual_threshold_unless_explicitly_stopped(http_peer, tmp_path, mode, stop):
    result, ui, _ = run_case(http_peer, tmp_path, mode, {
        "source": {"returned": 1}, "observe": {"returned": 1, "records": [SECRET]},
    }, [constraint("field_compare", "returned", ">=", from_source("returned")),
        constraint("collection_length", "records", "==", from_source("returned"))],
        source_checks=[constraint("field_compare", "returned", ">=", 2)], stop=stop)
    assert [step.status for step in result.steps] == [
        "COMPLETED", "FAILED", "BLOCKED" if stop else "PASSED", "BLOCKED" if stop else "COMPLETED"]
    assert result.status == "FAILED"
    if stop:
        assert result.steps[2].resolved_bindings == {}
        assert result.steps[2].blocked_by == result.steps[3].blocked_by == ["source"]
        assert ui.actions == ["open", "click"]
    else:
        assert list(result.steps[2].resolved_bindings.values()) == [1]
        assert result.steps[2].after_failures == result.steps[3].after_failures == ["source"]
        assert ui.actions == ["open", "click", "click", "click"]
    assert_traffic(http_peer, mode, result, ui, ["source"] if stop else ["source", "observe"])
    assert_safe_report(result)
