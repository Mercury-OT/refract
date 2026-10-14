"""Real Chromium regressions for unsupported transport and trace integrity.

The nonsecure HTTP case uses the local HTTP peer as an explicit proxy. The peer
serves absolute-form requests or a tunnel on its own socket and never forwards.
"""
import re
from urllib.parse import urlsplit

import pytest

from refracto.projection import frontend
from tests.browser.adapter import SyntheticUi, fields
from tests.browser.test_support import act, browser_lab, fixture, run_live, synthetic_scenario
from tests.fakes import FakeAuth, FakeNormalizer


APPLICATION_TRACE = "00-11111111111111111111111111111111-2222222222222222-01"
TRACE = re.compile(r"00-[0-9a-f]{32}-[0-9a-f]{16}-01")


def assert_fresh_trace(recorded, received):
    forwarded = received["traceparents"]
    assert len(forwarded) == 1
    traceparent = forwarded[0]
    assert TRACE.fullmatch(traceparent)
    assert traceparent != APPLICATION_TRACE
    assert "," not in traceparent
    assert traceparent == recorded.request.traceparent
    assert traceparent.split("-")[1] == recorded.trace_id
    assert not any(name.lower().startswith("x-refract-") for name in received["headers"])
    assert APPLICATION_TRACE not in received["headers"].values()


@pytest.mark.parametrize("target", ["beacon", "native-form"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_unsupported_beacon_and_native_form_never_send_backend_data(browser_lab, http_peer, target, mode):
    secret = "synthetic-unsupported-request-credential-763"
    plan = [fixture("must-not-be-consumed", "api/" + target)] if mode == "mock" else None
    support, context = browser_lab(mode=mode, mock_plan=plan,
        options={"extra_http_headers": {"Authorization": secret}})
    assert fields(support.snapshot(context))["staticLoaded"] is True
    assert {r["path"] for r in http_peer.requests} >= {"/", "/static/ready.js"}
    assert all(r["method"] == "GET" for r in http_peer.requests)
    act(support, context, "#value", action="fill", mode=mode, value="synthetic-beacon-body-secret-390")
    with pytest.raises(Exception) as error:
        act(support, context, "#" + target, mode=mode)
    assert secret not in str(error.value)
    assert "synthetic-beacon-body-secret-390" not in str(error.value)
    assert "synthetic-form-body-secret-498" not in str(error.value)
    assert http_peer.api_requests == []
    assert not any(r["method"] == "POST" for r in http_peer.requests)


@pytest.mark.parametrize("target", ["beacon", "native-form"])
@pytest.mark.parametrize("mode", ["live", "mock"])
def test_unsupported_transport_core_error_blocks_the_next_primitive(http_peer, target, mode):
    ui = SyntheticUi(http_peer.base_url, context_options={
        "extra_http_headers": {"Authorization": "synthetic-core-credential-290"}})
    scenario = synthetic_scenario(target)
    scenario.steps[1].request.path = "api/" + target
    if mode == "live":
        result = run_live(scenario, ui)
    else:
        result = frontend.run(scenario, ui=ui, auth=FakeAuth(), normalizer=FakeNormalizer(),
            mock_plan=[fixture("unsupported", "api/" + target), fixture("later")])
    assert [step.status for step in result.steps] == ["COMPLETED", "ERROR", "BLOCKED"]
    assert ui.actions == ["open", "click"]
    assert ui.close_calls == 1
    assert fields(ui.results[0].evidence.rendered)["staticLoaded"] is True
    assert result.mock_consumption == []
    assert result.provider_recordings == []
    assert http_peer.api_requests == []
    assert not any(r["method"] == "POST" for r in http_peer.requests)


@pytest.mark.parametrize("target", ["xhr-trace", "fetch-trace"])
def test_existing_mixed_case_trace_header_is_replaced_once_and_remains_core_valid(browser_lab, http_peer, target):
    support, context = browser_lab()
    actions = [act(support, context, "#" + target), act(support, context, "#" + target)]
    traffic = [action.traffic[0] for action in actions]
    assert all(len(action.traffic) == 1 for action in actions)
    assert len(http_peer.api_requests) == 2
    for item, received in zip(traffic, http_peer.api_requests):
        assert item.request == item.response.request
        assert item.request_id == item.response.request_id
        assert_fresh_trace(item.response, received)
    support.close(context)

    ui = SyntheticUi(http_peer.base_url)
    scenario = synthetic_scenario(target)
    for step in scenario.steps[1:]:
        step.target = target
        step.request.path = "api/" + target
    result = run_live(scenario, ui)
    assert result.status == "PASSED", [(step.status, step.detail) for step in result.steps]
    assert len(http_peer.api_requests) == 4
    for recorded, received in zip(result.provider_recordings, http_peer.api_requests[2:]):
        assert_fresh_trace(recorded, received)
    records = [item.response for item in traffic] + result.provider_recordings
    assert len({item.trace_id for item in records}) == 4
    assert len({item.request_id for item in records}) == 4


def test_nonsecure_http_fetch_and_xhr_use_local_proxy_and_valid_fresh_identities(browser_lab, http_peer):
    base_url = "http://example.com/".removesuffix("/")
    options = {"proxy": {"server": http_peer.base_url}}
    support, context = browser_lab(base_url=base_url, options=options)
    rendering = fields(support.snapshot(context))
    assert rendering["url"] == base_url + "/"
    assert rendering["secureContext"] is False
    assert rendering["randomUuidAvailable"] is False
    assert rendering["staticLoaded"] is True
    evidence = [act(support, context, target) for target in ("#fetch", "#xhr", "#fetch", "#xhr")]
    traffic = [item.traffic[0] for item in evidence]
    assert all(len(item.traffic) == 1 for item in evidence)
    assert len(http_peer.api_requests) == 4
    assert len({item.request_id for item in traffic}) == 4
    assert len({item.response.trace_id for item in traffic}) == 4
    for item, received in zip(traffic, http_peer.api_requests):
        assert isinstance(item.request_id, str) and item.request_id
        assert item.request_id == item.response.request_id
        assert item.request.body == received["body"] == {"value": "initial"}
        assert item.response.json["data"]["body"] == received["body"]
        assert_fresh_trace(item.response, received)
    assert http_peer.tunnels and set(http_peer.tunnels) == {"example.com:80"}
    assert all(urlsplit(request["url"]).hostname == "example.com" or
               next(value for name, value in request["headers"].items() if name.lower() == "host") == "example.com"
               for request in http_peer.requests)
    support.close(context)

    ui = SyntheticUi(base_url, context_options=options)
    scenario = synthetic_scenario()
    scenario.steps[2].target = "xhr"
    scenario.steps[2].request.path = "api/xhr"
    result = run_live(scenario, ui)
    assert result.status == "PASSED", [(step.status, step.detail) for step in result.steps]
    assert len(http_peer.api_requests) == 6
    for recorded, received in zip(result.provider_recordings, http_peer.api_requests[4:]):
        assert_fresh_trace(recorded, received)
