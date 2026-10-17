"""Reference HTTP transport preserves declared query meaning on a second peer."""
from urllib.parse import parse_qs, urlsplit

import pytest

from adapters.demo.api import DemoApiDriver
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer
from adapters.demo.resolver import DemoResolver
from refracto import ports
from refracto.declaration.model import Assertion, Expect, Input, RequestTemplate, Scenario, Step, ValueRef
from refracto.projection import backend, contract, e2e
from refracto.recorder import InMemoryRecorder
from tests.browser.conftest import http_peer
from tests.fakes import FakeAuth


@pytest.mark.parametrize("projection", ["backend", "e2e"])
def test_reference_driver_sends_encoded_queries_and_retains_decoded_evidence(http_peer, projection):
    declared = {"category": ValueRef("input", "category"), "page": 0, "enabled": False,
                "ratio": 1.5, "empty": "", "a&b": "one=two+three%/four"}
    wire = {"category": "caf\u00e9 \u96ea", "page": "0", "enabled": "false",
            "ratio": "1.5", "empty": "", "a&b": "one=two+three%/four"}
    scenario = Scenario("synthetic.reference.query", None, "editor", [], [Input("category", wire["category"])],
        "Transport independent catalog query values", [
            Step("search", RequestTemplate("GET", "api/catalog", query=declared),
                 Expect(response=[Assertion("success"), Assertion("field_equals", {"field": "path", "value": "/api/catalog"})])),
            Step("empty", RequestTemplate("GET", "api/catalog", query={}), Expect(response=[Assertion("success")])),
        ])
    api = DemoApiDriver(DemoConfig(http_peer.base_url))
    normalizer = DemoResponseNormalizer()
    common = dict(auth=FakeAuth(), api=api, state=None, recorder=InMemoryRecorder(),
                  resolve_request=DemoResolver().resolve_request, normalizer=normalizer)
    result = backend.run(scenario, **common) if projection == "backend" else e2e.run(scenario, ui=None, **common)
    assert result.status == "PASSED", [(s.status, s.detail) for s in result.steps]
    assert len(http_peer.api_requests) == 2
    first, second = http_peer.api_requests
    assert first["path"] == second["path"] == "/api/catalog"
    assert parse_qs(urlsplit(first["url"]).query, keep_blank_values=True) == {k: [v] for k, v in wire.items()}
    assert second["url"] == "/api/catalog"
    assert [r.request.query for r in result.provider_recordings] == [wire, {}]
    assert all(r.request.path == "api/catalog" for r in result.provider_recordings)
    checked = contract.run(scenario, result.provider_recordings, normalizer, execution_steps=result.steps)
    assert checked.status == "PASSED"
    assert len(http_peer.api_requests) == 2  # Contract reads recordings without sending.


@pytest.mark.parametrize("path", ["api/catalog?unexpected=1", "api/catalog#fragment"])
def test_reference_driver_rejects_embedded_query_or_fragment_before_send(http_peer, path):
    api = DemoApiDriver(DemoConfig(http_peer.base_url))
    with pytest.raises(ValueError):
        api.send(ports.RequestSpec("GET", path, query={"category": "guide"}), {})
    assert http_peer.requests == []
