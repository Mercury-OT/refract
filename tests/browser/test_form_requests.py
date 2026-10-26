"""Actual mixed JSON/form traffic through unchanged Scenario and core checks."""
import json
from pathlib import Path

import pytest
import yaml

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from tests.browser.adapter import SyntheticUi
from tests.browser.test_support import act, browser_lab
from tests.fakes import FakeAuth, FakeNormalizer


FORM = "application/x-www-form-urlencoded"
EXAMPLE = Path(__file__).resolve().parents[2] / "examples/browser-form-requests/mixed_requests.yaml"


def fixture(identity="form", path="api/form", reply="shared sample"):
    return ports.MockResponse(fixture_id=identity, source="independent mixed-body fixture",
        method="POST", path=path, response={"success": True, "data": {"reply": reply}})


def configure(context, requests):
    context.page.evaluate("requests => { window.lab.formRequests = requests; }", requests)


def content_type(received):
    return next(value for name, value in received["header_items"] if name.lower() == "content-type")


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("target", ["#form-fetch", "#form-xhr"])
def test_actual_form_fields_decode_once_and_server_receives_unchanged_bytes(browser_lab, http_peer, mode, target):
    raw = "caf%C3%A9=%E9%9B%AA+space%2B%26%3D%25%2F&empty=&bare&zero=0&false=false&null=null&dot.key=x&list%5B0%5D=y&once=%252F"
    expected = {"caf\u00e9": "\u96ea space+&=%/", "empty": "", "bare": "", "zero": "0",
                "false": "false", "null": "null", "dot.key": "x", "list[0]": "y", "once": "%2F"}
    support, context = browser_lab(mode=mode, mock_plan=[fixture()] if mode == "mock" else None)
    configure(context, [{"path": "/api/form", "raw": raw, "headerValues": [FORM]}])
    evidence = act(support, context, target, mode=mode)
    traffic, = evidence.traffic
    assert traffic.request.body == expected
    assert traffic.response.request.body == expected
    assert traffic.response.request.body is not traffic.request.body
    assert traffic.request_id == traffic.response.request_id
    assert traffic.step_id == traffic.response.step_id == evidence.step_id
    assert traffic.response.trace_id == traffic.request.traceparent.split("-")[1]
    assert any(name.lower() == "content-type" and value.lower().startswith(FORM)
               for name, value in traffic.response.request_header_items)
    if mode == "live":
        received, = http_peer.api_requests
        assert received["raw_body"] == raw.encode()
        assert content_type(received).lower().startswith(FORM)
        assert received["body"] == expected
        assert received["traceparents"] == [traffic.request.traceparent]
        assert not any(name.lower().startswith("x-refract-") for name in received["headers"])
    else:
        assert http_peer.api_requests == []
        assert context.mock_queue.index == 1
        assert traffic.mock_fixture_id == "form"


class FormUi(SyntheticUi):
    def __init__(self, base_url, requests=None, mutate=None):
        super().__init__(base_url)
        self.requests, self.mutate = requests, mutate

    def perform_step(self, scenario, step, context, permit):
        result = super().perform_step(scenario, step, context, permit)
        if step.action == "open" and self.requests is not None:
            configure(context, self.requests)
        if self.mutate and step.id == "form_submit" and result.evidence.traffic:
            self.mutate(result)
        return result


def run_example(http_peer, mode, *, path=EXAMPLE, requests=None, mutate=None):
    ui = FormUi(http_peer.base_url, requests, mutate)
    adapters = Adapters(FakeAuth(), None, None, ui, InMemoryRecorder, None, FakeNormalizer())
    report = run_scenario(path, adapters,
        projections=("frontend" if mode == "mock" else "e2e",),
        mock_plan=[fixture("json", "api/echo"), fixture()] if mode == "mock" else None)
    return report, ui


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_loaded_example_handles_json_and_form_in_one_run(http_peer, mode):
    report, ui = run_example(http_peer, mode)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert [step.status for step in report.domains[0].steps] == ["COMPLETED", "COMPLETED", "PASSED", "PASSED"]
    assert ui.actions == ["open", "fill", "click", "click"]
    assert ui.close_calls == 1
    first, second = [ui.results[index].evidence.traffic[0] for index in (2, 3)]
    assert first.request.body == second.request.body == {"value": "shared sample"}
    assert first.request_id != second.request_id
    assert first.step_id == "json_submit" and second.step_id == "form_submit"
    if mode == "live":
        json_request, form_request = http_peer.api_requests
        assert json_request["raw_body"] == b'{"value":"shared sample"}'
        assert content_type(json_request) == "application/json"
        assert form_request["raw_body"] == b"value=shared+sample"
        assert content_type(form_request).lower() == FORM + ";charset=utf-8"
        assert form_request["body"] == json_request["body"] == {"value": "shared sample"}
    else:
        assert http_peer.api_requests == []
        assert [first.mock_fixture_id, second.mock_fixture_id] == ["json", "form"]


def changed_example(tmp_path, change):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "changed.yaml"
    path.write_text(yaml.safe_dump(json.loads(json.dumps(raw)), sort_keys=False), encoding="utf-8")
    return path


def append_after(raw):
    raw["steps"].append({"id": "after", "do": "click", "target": "noop"})


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("observed,expected", [
    ("value=wrong", "shared sample"), ("other=shared+sample", "shared sample"),
    ("value=0", 0), ("value=false", False), ("value=null", None),
])
def test_wrong_missing_or_coerced_business_values_fail_and_continue(http_peer, tmp_path, mode, observed, expected):
    def change(raw):
        raw["steps"][-1]["expect"]["request"]["body"] = {"value": expected}
        append_after(raw)
    path = changed_example(tmp_path, change)
    report, ui = run_example(http_peer, mode, path=path,
        requests=[{"path": "/api/form", "raw": observed, "headerValues": [FORM]}])
    assert report.status == "FAILED"
    assert report.domains[0].steps[-2].status == "FAILED"
    assert [(check.check, check.ok) for check in report.domains[0].steps[-2].checks
            if check.check == "request"] == [("request", False)]
    assert report.domains[0].steps[-1].status == "COMPLETED"
    assert ui.actions == ["open", "fill", "click", "click", "click"]
    assert len(http_peer.api_requests) == (2 if mode == "live" else 0)


INVALID_REQUESTS = [
    {"raw": "value=one&value=two"},
    {"raw": "value=one&%76alue=two"},
    {"raw": "a+b=one&a%20b=two"},
    {"raw": "=empty-name"},
    {"raw": "value=%"},
    {"raw": "value=%2Z"},
    {"raw": "value=%FF"},
    {"bytes": [118, 61, 255]},
    {"bytes": [118, 61, 49], "headerValues": [FORM + ";charset=iso-8859-1"]},
    {"bytes": [118, 61, 49], "headerValues": [FORM + ";charset=utf-8;charset=utf-8"]},
    {"bytes": [118, 61, 49], "headerValues": [FORM + ";boundary=x"]},
    {"raw": "value=one", "headerValues": [FORM, "application/json"]},
    {"raw": "value=one", "headerValues": ["application/json", FORM]},
    {"raw": "{}", "headerValues": [FORM + ";charset=unsupported"]},
    {"bytes": list(b"value=one"), "headerValues": []},
]


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("input_request", INVALID_REQUESTS)
def test_invalid_forms_fail_before_forwarding_or_mock_consumption(browser_lab, http_peer, mode, input_request):
    support, context = browser_lab(mode=mode, mock_plan=[fixture()] if mode == "mock" else None)
    configured = {"path": "/api/form", "headerValues": [FORM], **input_request}
    configure(context, [configured])
    with pytest.raises(RuntimeError) as error:
        act(support, context, "#form-fetch", mode=mode)
    assert str(error.value) == "browser action or evidence collection failed"
    assert context.errors == ["browser request transport or recording failed"]
    assert context.mock_queue.index == 0
    assert http_peer.api_requests == []
    assert context.closed


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_repeated_content_type_via_xhr_is_rejected(browser_lab, http_peer, mode):
    support, context = browser_lab(mode=mode, mock_plan=[fixture()] if mode == "mock" else None)
    configure(context, [{"path": "/api/form", "raw": "value=one", "headerValues": [FORM, FORM]}])
    with pytest.raises(RuntimeError):
        act(support, context, "#form-xhr", mode=mode)
    assert context.mock_queue.index == 0
    assert http_peer.api_requests == []


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_unusable_sensitive_body_is_error_and_blocks_later_actions(http_peer, tmp_path, mode):
    sentinel = "private-form-sample-72819"
    path = changed_example(tmp_path, append_after)
    report, ui = run_example(http_peer, mode, path=path,
        requests=[{"path": "/api/form", "raw": f"secret={sentinel}&secret=again", "headerValues": [FORM]}])
    assert report.status != "PASSED"
    assert [step.status for step in report.domains[0].steps][-2:] == ["ERROR", "BLOCKED"]
    assert ui.actions == ["open", "fill", "click", "click"]
    assert sentinel not in repr(report)
    assert sentinel not in repr(report.domains[0])
    assert sentinel not in report.domains[0].steps[-2].detail
    assert len(http_peer.api_requests) == (1 if mode == "live" else 0)


@pytest.mark.parametrize("configured", [{"pairs": []}, {"raw": ""}, {"raw": None}])
def test_empty_and_absent_form_bodies_follow_real_browser_observation(browser_lab, http_peer, configured):
    support, context = browser_lab()
    observed = []
    context.browser_context.on("request", lambda request:
        observed.append(request.post_data_buffer) if request.url.endswith("/api/form") else None)
    configure(context, [{"path": "/api/form", "headerValues": [FORM], **configured}])
    traffic, = act(support, context, "#form-fetch").traffic
    assert len(observed) == 1
    assert observed[0] in (None, b"")
    assert traffic.request.body == (None if observed[0] is None else {})
    assert http_peer.api_requests[0]["raw_body"] == b""


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_json_with_non_form_header_keeps_existing_behavior(browser_lab, http_peer, mode):
    support, context = browser_lab(mode=mode, mock_plan=[fixture()] if mode == "mock" else None)
    configure(context, [{"path": "/api/form", "raw": '{"value":"json text"}',
                         "headerValues": ["text/plain"]}])
    traffic, = act(support, context, "#form-fetch", mode=mode).traffic
    assert traffic.request.body == {"value": "json text"}
    assert len(http_peer.api_requests) == (1 if mode == "live" else 0)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_repeated_form_endpoint_preserves_distinct_requests(browser_lab, http_peer, mode):
    plan = [fixture("first", reply="first response"), fixture("second", reply="second response")]
    support, context = browser_lab(mode=mode, mock_plan=plan if mode == "mock" else None)
    configure(context, [{"path": "/api/form", "pairs": [["value", value]]} for value in ("first", "second")])
    traffic = act(support, context, "#form-multi", mode=mode).traffic
    assert len(traffic) == 2
    by_value = {item.request.body["value"]: item for item in traffic}
    assert set(by_value) == {"first", "second"}
    first, second = by_value["first"], by_value["second"]
    assert first.request_id != second.request_id
    for item in traffic:
        assert item.response.request_id == item.request_id
        assert item.response.request.body == item.request.body
    if mode == "mock":
        assert [first.mock_fixture_id, second.mock_fixture_id] == ["first", "second"]
        assert [first.response.json["data"]["reply"], second.response.json["data"]["reply"]] == ["first response", "second response"]
        assert context.mock_queue.index == 2
        assert http_peer.api_requests == []
    else:
        assert sorted(request["raw_body"] for request in http_peer.api_requests) == [b"value=first", b"value=second"]
        assert all(item.response.json["data"]["reply"] == item.request.body["value"] for item in traffic)


def test_unassigned_form_stays_diagnostic(browser_lab):
    support, context = browser_lab()
    first = act(support, context, "#form-timer")
    second = act(support, context, "#delayed")
    assert first.traffic == []
    matches = [record for record in first.diagnostic_recorded + second.diagnostic_recorded
               if record.request.path == "api/form"]
    assert len(matches) == 1
    assert matches[0].request.body == {"value": "initial"}
    assert matches[0].step_id is None
    assert all(item.request.path == "api/delayed" for item in second.traffic)


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_matching_unassigned_form_cannot_satisfy_step(http_peer, tmp_path, mode):
    def change(raw):
        raw["steps"][-1]["target"] = "form-timer"
        append_after(raw)
    report, ui = run_example(http_peer, mode, path=changed_example(tmp_path, change))
    assert report.status != "PASSED"
    assert [step.status for step in report.domains[0].steps][-2:] == ["ERROR", "BLOCKED"]
    assert ui.results[-1].evidence.traffic == []


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_form_evidence_tampering_is_rejected(http_peer, mode):
    def mutate(result):
        result.evidence.traffic[0].response.request.body["value"] = "rewritten"
    report, ui = run_example(http_peer, mode, mutate=mutate)
    assert report.status != "PASSED"
    assert report.domains[0].steps[-1].status == "ERROR"
    assert "pairing mismatch" in report.domains[0].steps[-1].detail
