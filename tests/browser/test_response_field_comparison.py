"""Complete response-field comparison through actual Chromium responses.

The page's payload queue and mock response queue are independent fixtures.
Neither the page nor its adapter consults Scenario assertions.
"""
import copy

import pytest

from refracto import ports
from refracto.declaration.model import (
    Assertion, Binding, Expect, RequestTemplate, Scenario, Step, ValueRef,
)
from refracto.projection import e2e, frontend
from refracto.recorder import InMemoryRecorder
from refracto.report import RunReport
from tests.browser.adapter import SyntheticUi
from tests.fakes import FakeAuth, FakeNormalizer


SECRET = "synthetic-nested-comparison-sentinel-317"


class PayloadUi(SyntheticUi):
    """Configure a neutral page-owned action independently of expected values."""

    def __init__(self, base_url, payloads):
        super().__init__(base_url)
        self.payloads = copy.deepcopy(payloads)

    def perform_step(self, scenario, step, context, permit):
        result = super().perform_step(scenario, step, context, permit)
        if step.action == "open":
            context.page.evaluate("""payloads => {
                const button = document.createElement('button');
                button.id = 'comparison';
                button.textContent = 'Read fixture content';
                document.body.appendChild(button);
                let cursor = 0;
                button.addEventListener('click', () => {
                    const payload = payloads[cursor++];
                    return fetch('/api/comparison', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: payload})
                    }).then(response => response.json()).then(body => {
                        document.querySelector('#result').textContent = JSON.stringify(body);
                    });
                });
            }""", self.payloads)
        return result


def fixtures(payloads):
    return [ports.MockResponse(
        fixture_id=f"comparison-fixture-{index}",
        source="independent complete response-field fixture",
        method="POST", path="api/comparison",
        response={"success": True, "data": {"reply": copy.deepcopy(payload)}},
    ) for index, payload in enumerate(payloads)]


def declaration(payloads, check, *, use_reference=True, expected=None):
    before, after = payloads
    request = lambda payload: RequestTemplate("POST", "api/comparison", {"value": payload})
    return Scenario("synthetic.response_field_comparison", None, "editor", [], [],
        "Compare complete observations from two actual browser actions", [
        Step("open", None, Expect(), action="open", target="laboratory"),
        Step("before", request(before), Expect(response=[
            Assertion("status_equals", {"value": 200}), Assertion("success"),
            Assertion("has", {"field": "reply"}),
        ]), action="click", target="comparison", request_asserted=True),
        Step("after", request(after), Expect(response=[
            Assertion("status_equals", {"value": 200}), Assertion("success"),
            Assertion(check, {"field": "reply", "value": (
                ValueRef("bind", "baseline") if use_reference else expected)}),
        ]), bind=[Binding("baseline", "before", "reply")] if use_reference else [],
             action="click", target="comparison", request_asserted=True),
        Step("continued", None, Expect(), action="click", target="noop"),
    ])


def run_comparison(http_peer, mode, payloads, check="field_equals", *,
                   normalizer=None, use_reference=True, expected=None):
    ui = PayloadUi(http_peer.base_url, payloads)
    scenario = declaration(payloads, check, use_reference=use_reference, expected=expected)
    kwargs = dict(ui=ui, auth=FakeAuth(), normalizer=normalizer or FakeNormalizer())
    if mode == "mock":
        result = frontend.run(scenario, mock_plan=fixtures(payloads), **kwargs)
    else:
        result = e2e.run(scenario, recorder=InMemoryRecorder(), state=None, **kwargs)
    return result, ui


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("check", ["field_equals", "field_not_equals"])
@pytest.mark.parametrize("before,after,equal", [
    ({"title": "record", "content": {"tags": ["one", "two"], "flag": False}},
     {"content": {"flag": False, "tags": ["one", "two"]}, "title": "record"}, True),
    ({"content": {"tags": ["one", "two"]}},
     {"content": {"tags": ["one", "two"], "extra": None}}, False),
    ([{"value": 1}, {"value": 2}], [{"value": 2}, {"value": 1}], False),
    ({"content": [False, True]}, {"content": [0, 1]}, False),
    ([None, {}, []], [None, {}, []], True),
], ids=["complete-object", "extra-nested-key", "ordered-list", "bool-int", "null-empty"])
def test_actual_browser_complete_comparisons_and_continuation(http_peer, mode, check, before, after, equal):
    result, ui = run_comparison(http_peer, mode, [before, after], check)
    passed = equal if check == "field_equals" else not equal
    assert [step.status for step in result.steps] == [
        "COMPLETED", "PASSED", "PASSED" if passed else "FAILED", "COMPLETED",
    ]
    assert result.status == ("PASSED" if passed else "FAILED")
    assert result.steps[2].resolved_bindings == {"baseline": before}
    assert result.steps[3].after_failures == ([] if passed else ["after"])
    assert ui.actions == ["open", "click", "click", "click"]
    assert ui.close_calls == 1
    observed = [outcome.evidence.traffic[0].response.json["data"]["reply"]
                for outcome in ui.results[1:3]]
    assert observed == [before, after]
    if mode == "live":
        assert [item["body"] for item in http_peer.api_requests] == [
            {"value": before}, {"value": after},
        ]
        assert [record.step_id for record in result.provider_recordings] == ["before", "after"]
    else:
        assert http_peer.api_requests == []
        assert len(result.mock_consumption) == 2


class MissingReplyNormalizer(FakeNormalizer):
    def __init__(self, missing_call):
        self.calls = 0
        self.missing_call = missing_call

    def normalize(self, response):
        self.calls += 1
        normalized = super().normalize(response)
        if self.calls == self.missing_call:
            normalized.fields.pop("reply")
        return normalized


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("check", ["field_equals", "field_not_equals"])
def test_missing_current_field_fails_both_comparisons(http_peer, mode, check):
    result, ui = run_comparison(http_peer, mode, [{"value": 1}, {"value": 2}], check,
                                normalizer=MissingReplyNormalizer(2))
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "FAILED", "COMPLETED"]
    comparison, = [item for item in result.steps[2].checks if item.check == check]
    assert not comparison.ok
    assert "missing" in comparison.detail
    assert len(ui.results[2].evidence.traffic) == 1


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("source", ["missing", "null"])
def test_unavailable_source_blocks_before_next_browser_action(http_peer, mode, source):
    before = None if source == "null" else {"value": "source"}
    result, ui = run_comparison(http_peer, mode, [before, {"value": "next"}],
        "field_not_equals", normalizer=MissingReplyNormalizer(1) if source == "missing" else None)
    assert [step.status for step in result.steps] == [
        "COMPLETED", "FAILED" if source == "missing" else "PASSED", "BLOCKED", "COMPLETED",
    ]
    assert result.steps[2].resolved_bindings == {}
    assert result.steps[2].blocked_by == ["before"]
    assert result.status != "PASSED"
    assert ui.actions == ["open", "click", "click"]
    assert len(http_peer.api_requests) == (1 if mode == "live" else 0)
    assert len([outcome for outcome in ui.results if outcome.evidence.traffic]) == 1


class ReusedBufferNormalizer(FakeNormalizer):
    def __init__(self):
        self.buffer = {"reply": {"nested": []}}

    def normalize(self, response):
        normalized = super().normalize(response)
        # Reuse both the enclosing map and a nested mutable container. The
        # previous response observation must not change with this buffer.
        self.buffer["reply"]["nested"][:] = normalized.fields["reply"]["nested"]
        normalized.fields = self.buffer
        return normalized


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_previous_observation_survives_normalizer_buffer_reuse(http_peer, mode):
    before, after = {"nested": ["original"]}, {"nested": ["modified"]}
    normalizer = ReusedBufferNormalizer()
    result, ui = run_comparison(http_peer, mode, [before, after], normalizer=normalizer)
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "FAILED", "COMPLETED"]
    assert result.steps[2].resolved_bindings == {"baseline": before}
    assert normalizer.buffer["reply"] == after
    assert ui.results[1].evidence.traffic[0].response.json["data"]["reply"] == before


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("invalid", ["cycle", "non-finite"])
def test_invalid_observed_containers_are_errors_not_inequality(http_peer, mode, invalid):
    class InvalidNormalizer(FakeNormalizer):
        def __init__(self):
            self.calls = 0

        def normalize(self, response):
            self.calls += 1
            normalized = super().normalize(response)
            if self.calls == 2:
                broken = {"value": float("nan")}
                if invalid == "cycle":
                    broken = []
                    broken.append(broken)
                normalized.fields["reply"] = broken
            return normalized

    result, ui = run_comparison(http_peer, mode, [{"value": 1}, {"value": 2}],
        "field_not_equals", normalizer=InvalidNormalizer(), use_reference=False, expected="different type")
    assert [step.status for step in result.steps] == ["COMPLETED", "PASSED", "ERROR", "BLOCKED"]
    assert result.status == "FAILED"
    assert ui.actions == ["open", "click", "click"]


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("check", ["field_equals", "field_not_equals"])
def test_nested_comparison_diagnostics_and_default_report_do_not_disclose_values(http_peer, mode, check):
    before = {SECRET: {"content": [SECRET, False]}}
    after = copy.deepcopy(before) if check == "field_not_equals" else {SECRET: {"content": [SECRET, 0]}}
    result, _ = run_comparison(http_peer, mode, [before, after], check)
    assert result.steps[2].status == "FAILED"
    report = RunReport("synthetic.response_field_comparison", [result])
    assert report.status == "FAILED"
    assert SECRET not in repr(report)
    assert SECRET not in str(report.localize())
    assert all(SECRET not in step.detail for step in result.steps)
    assert all(SECRET not in item.detail for item in result.checks)
