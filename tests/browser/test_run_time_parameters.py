"""Real browser input/request evidence uses the same frozen UTC parameter."""
from copy import deepcopy
import json

import pytest
import yaml

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from tests.browser.adapter import SyntheticUi, fields
from tests.fakes import FakeAuth, FakeNormalizer


BASE = "2026-10-24T08:00:00.000Z"
EXPIRATION = "2026-10-31T08:00:00.000Z"


def declaration(tmp_path):
    parameter = {"from_parameter": "expires_at"}
    raw = {
        "schema_version": 1, "scenario": "synthetic.run_time", "users": ["editor"],
        "parameters": {"expires_at": {"from_run": "time", "offset": {"days": 7}}},
        "steps": [
            {"id": "open", "do": "open", "target": "laboratory"},
            {"id": "fill", "do": "fill", "target": "value", "value": parameter},
            {"id": "first", "do": "click", "target": "fetch", "expect": {
                "request": {"method": "POST", "path": ["api", "echo"], "body": {"value": parameter}},
                "response": [{"check": "status_equals", "value": 200},
                             {"check": "field_equals", "field": "reply", "value": parameter}]}},
            {"id": "second", "do": "click", "target": "fetch", "expect": {
                "request": {"method": "POST", "path": ["api", "echo"], "body": {"value": parameter}},
                "response": [{"check": "status_equals", "value": 200},
                             {"check": "field_equals", "field": "reply", "value": parameter}]}},
        ],
    }
    path = tmp_path / "run-time.yaml"
    path.write_text(yaml.safe_dump(json.loads(json.dumps(raw)), sort_keys=False), encoding="utf-8")
    return path


def mock_plan(value=EXPIRATION):
    return [ports.MockResponse(fixture_id=f"time-{index}", source="fixed independent echo fixture",
                              method="POST", path="api/echo",
                              response={"success": True, "data": {"reply": value}})
            for index in range(2)]


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_frozen_time_reaches_browser_and_response(http_peer, tmp_path, mode):
    ui = SyntheticUi(http_peer.base_url)
    adapters = Adapters(FakeAuth(), None, None, ui, InMemoryRecorder, None, FakeNormalizer())
    report = run_scenario(declaration(tmp_path), adapters,
                          projections=("frontend" if mode == "mock" else "e2e",),
                          mock_plan=mock_plan() if mode == "mock" else None, run_time=BASE)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert report.run_time == BASE and report.run_time_source == "fixed"
    assert report.run_time_values == {"expires_at": EXPIRATION}
    assert BASE not in repr(report) and EXPIRATION not in repr(report)
    assert ui.actions == ["open", "fill", "click", "click"]
    assert ui.close_calls == 1
    assert fields(ui.results[1].evidence.rendered)["value"] == EXPIRATION
    traffic = [ui.results[index].evidence.traffic[0] for index in (2, 3)]
    assert [item.request.body["value"] for item in traffic] == [EXPIRATION, EXPIRATION]
    assert [item.response.json["data"]["reply"] for item in traffic] == [EXPIRATION, EXPIRATION]
    assert len(http_peer.api_requests) == (0 if mode == "mock" else 2)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("observed", [None, False, 0, {}, [], "2026-10-30T08:00:00.000Z"])
def test_wrong_browser_time_evidence_cannot_satisfy_exact_check(http_peer, tmp_path, mode, observed):
    class WrongTimeNormalizer(FakeNormalizer):
        def normalize(self, response):
            normalized = super().normalize(response)
            normalized.fields["reply"] = deepcopy(observed)
            return normalized
    ui = SyntheticUi(http_peer.base_url)
    normalizer = WrongTimeNormalizer() if mode == "live" else FakeNormalizer()
    adapters = Adapters(FakeAuth(), None, None, ui, InMemoryRecorder, None, normalizer)
    report = run_scenario(declaration(tmp_path), adapters,
                          projections=("frontend" if mode == "mock" else "e2e",),
                          mock_plan=mock_plan(observed) if mode == "mock" else None, run_time=BASE)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps] == ["COMPLETED", "COMPLETED", "FAILED", "FAILED"]
    assert ui.actions == ["open", "fill", "click", "click"]
    assert ui.close_calls == 1
    traffic = [ui.results[index].evidence.traffic[0] for index in (2, 3)]
    assert [item.request.body["value"] for item in traffic] == [EXPIRATION, EXPIRATION]
    assert len(http_peer.api_requests) == (0 if mode == "mock" else 2)
