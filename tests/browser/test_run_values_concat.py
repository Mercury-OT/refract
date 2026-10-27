"""Real browser fill and outgoing evidence consume frozen and observed strings."""
from copy import deepcopy
import json
from urllib.request import Request, build_opener, ProxyHandler

import pytest
import yaml

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario
from tests.browser.adapter import SyntheticUi, fields
from tests.fakes import FakeAuth, FakeNormalizer


def declaration(tmp_path):
    parameter = {"from_parameter": "label"}
    combined = {"concat": [{"from_step": "first", "response_field": "reply"}, "-again"]}
    raw = {
        "schema_version": 1, "scenario": "synthetic.run_string_composition", "users": ["editor"],
        "parameters": {"token": {"from_run": "unique"},
                       "label": {"concat": ["start-", {"from_parameter": "token"}, "-end"]}},
        "steps": [
            {"id": "open", "do": "open", "target": "laboratory"},
            {"id": "fill", "do": "fill", "target": "value", "value": parameter},
            {"id": "first", "do": "click", "target": "fetch", "expect": {
                "request": {"method": "POST", "path": ["api", "echo"], "body": {"value": parameter}},
                "response": [{"check": "status_equals", "value": 200},
                             {"check": "field_equals", "field": "reply", "value": parameter}]}},
            {"id": "fill_again", "do": "fill", "target": "value", "value": combined},
            {"id": "second", "do": "click", "target": "fetch", "expect": {
                "request": {"method": "POST", "path": ["api", "echo"], "body": {"value": combined}},
                "response": [{"check": "status_equals", "value": 200},
                             {"check": "field_equals", "field": "reply", "value": combined}]}},
            {"id": "independent", "do": "click", "target": "noop"},
        ],
    }
    path = tmp_path / "run-values.yaml"
    path.write_text(yaml.safe_dump(json.loads(json.dumps(raw)), sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_frozen_run_value_and_response_concat_reach_actual_browser(http_peer, tmp_path, monkeypatch, mode):
    from refracto.declaration import run_values
    from types import SimpleNamespace
    # Reproducible synthetic input; response fixtures do not inspect assertions.
    sentinel = "0123456789abcdef0123456789abcdef"
    calls = []
    def generate():
        calls.append(True)
        return SimpleNamespace(hex=sentinel)
    monkeypatch.setattr(run_values, "uuid4", generate)
    ui = SyntheticUi(http_peer.base_url)
    adapters = Adapters(FakeAuth(), None, None, ui, InMemoryRecorder, None, FakeNormalizer())
    values = [f"start-{sentinel}-end", f"start-{sentinel}-end-again"]
    plan = [ports.MockResponse(fixture_id=f"run-value-{index}", source="independent echo fixture",
                              method="POST", path="api/echo", response={"success": True, "data": {"reply": value}})
            for index, value in enumerate(values)]
    report = run_scenario(declaration(tmp_path), adapters,
                          projections=("frontend" if mode == "mock" else "e2e",),
                          mock_plan=plan if mode == "mock" else None)
    assert report.status == "PASSED", report.localize()
    assert calls == [True]
    assert report.run_unique_values == {("frontend" if mode == "mock" else "e2e"): {"token": sentinel}}
    assert sentinel not in repr(report)
    assert report.degradations() == []
    assert ui.actions == ["open", "fill", "click", "fill", "click", "click"]
    assert ui.close_calls == 1
    assert [fields(ui.results[index].evidence.rendered)["value"] for index in (1, 3)] == values
    traffic = [ui.results[index].evidence.traffic[0] for index in (2, 4)]
    assert [item.request.body["value"] for item in traffic] == values
    assert [item.response.json["data"]["reply"] for item in traffic] == values
    assert len(http_peer.api_requests) == (0 if mode == "mock" else 2)


def test_all_projections_use_distinct_sources_and_contract_keeps_backend_values(http_peer, tmp_path, monkeypatch):
    """Actual HTTP and Chromium observe separate execution values on one peer."""
    from refracto.declaration import run_values
    from types import SimpleNamespace

    tokens = ["1" * 32, "2" * 32, "3" * 32]
    generated = []

    def generate():
        token = tokens[len(generated)]
        generated.append(token)
        return SimpleNamespace(hex=token)

    monkeypatch.setattr(run_values, "uuid4", generate)

    class PeerApi(ports.ApiDriver):
        def send(self, spec, session):
            headers = {"Content-Type": "application/json", **spec.headers}
            if spec.traceparent:
                headers["traceparent"] = spec.traceparent
            outgoing = Request(http_peer.base_url + "/" + spec.path,
                               data=json.dumps(spec.body).encode(),
                               headers=headers, method=spec.method)
            with build_opener(ProxyHandler({})).open(outgoing, timeout=5) as observed:
                text = observed.read().decode()
                return ports.RecordedResponse(observed.status, dict(observed.headers),
                    json.loads(text), text, spec.traceparent.split("-")[1], spec,
                    header_items=list(observed.headers.items()))

    ui = SyntheticUi(http_peer.base_url)
    adapters = Adapters(FakeAuth(), PeerApi(), None, ui, InMemoryRecorder,
        lambda action: ports.RequestSpec(
            action.method, action.path, action.body), FakeNormalizer())
    mock_values = [f"start-{tokens[1]}-end", f"start-{tokens[1]}-end-again"]
    plan = [ports.MockResponse(fixture_id=f"separate-{index}", source="independent fixed echo fixture",
            method="POST", path="api/echo", response={"success": True, "data": {"reply": value}})
            for index, value in enumerate(mock_values)]
    report = run_scenario(declaration(tmp_path), adapters, mock_plan=plan)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert generated == tokens
    assert report.run_unique_values == {
        "backend": {"token": tokens[0]}, "frontend": {"token": tokens[1]},
        "e2e": {"token": tokens[2]}, "contract": {"token": tokens[0]}}
    assert [item["body"]["value"] for item in http_peer.api_requests] == [
        f"start-{tokens[0]}-end", f"start-{tokens[0]}-end-again",
        f"start-{tokens[2]}-end", f"start-{tokens[2]}-end-again"]
    for index, token in enumerate(tokens[1:]):
        outcomes = ui.results[index * 6:(index + 1) * 6]
        assert fields(outcomes[1].evidence.rendered)["value"] == f"start-{token}-end"
        assert fields(outcomes[3].evidence.rendered)["value"] == f"start-{token}-end-again"
        assert outcomes[2].evidence.traffic[0].request.body["value"] == f"start-{token}-end"
    assert ui.close_calls == 2
    assert all(token not in repr(report) for token in tokens)


@pytest.mark.parametrize("mode", ["live", "mock"])
@pytest.mark.parametrize("observed", [None, False, 0, {}, []])
def test_bad_observed_operand_blocks_fill_without_repairing_evidence(http_peer, tmp_path, monkeypatch, mode, observed):
    class WrongTypeNormalizer(FakeNormalizer):
        def normalize(self, response):
            norm = super().normalize(response)
            norm.fields["reply"] = deepcopy(observed)
            return norm
    ui = SyntheticUi(http_peer.base_url)
    adapters = Adapters(FakeAuth(), None, None, ui, InMemoryRecorder, None, WrongTypeNormalizer())
    path = declaration(tmp_path)
    raw = yaml.safe_load(path.read_text())
    raw["steps"][2]["expect"]["response"] = [{"check": "status_equals", "value": 200}]
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    plan = [ports.MockResponse(fixture_id="observed", source="independent wrong-type fixture",
                              method="POST", path="api/echo", response={"success": True, "data": {"reply": observed}})]
    report = run_scenario(path, adapters, projections=("frontend" if mode == "mock" else "e2e",),
                          mock_plan=plan if mode == "mock" else None)
    assert report.status != "PASSED"
    assert [step.status for step in report.domains[0].steps] == [
        "COMPLETED", "COMPLETED", "PASSED", "BLOCKED", "BLOCKED", "COMPLETED"]
    assert ui.actions == ["open", "fill", "click", "click"]
    assert report.domains[0].steps[3].resolved_bindings == {}
    assert report.domains[0].steps[3].blocked_by == ["first"]
    assert len(http_peer.api_requests) == (0 if mode == "mock" else 1)
    assert ui.close_calls == 1
