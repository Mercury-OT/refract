"""The backend projection (refracto/projection/backend.py) driven live over real HTTP
against a locally-started demo-app server, using only the demo config/auth/api pieces.
This test exercises the request + response blocks (no backend_state/StateProbe) with an
inline synthetic Scenario and a small inline resolve_request — the StateProbe/Tier-3
path is covered by test_demo_state.py."""
from refracto import ports
from refracto.declaration.model import Assertion, Expect, Grid, RequestTemplate, Scenario, Step
from refracto.projection import backend
from refracto.recorder import InMemoryRecorder

from adapters.demo.api import DemoApiDriver
from adapters.demo.auth import DemoAuthenticator
from adapters.demo.config import DemoConfig
from adapters.demo.normalizer import DemoResponseNormalizer


def resolve_request(scenario, step, template):
    return ports.RequestSpec(
        method=template.method,
        path=template.path,
        body=(template.body or {"name": "demo", "rows": [1, 2, 3]}),
    )


def _scenario() -> Scenario:
    return Scenario(
        id="demo_item_create_backend_inline",
        grid=Grid(level="smoke", module="demo"),
        actor="tester",
        precondition=[],
        inputs=[],
        intent="create an item via POST /items",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="POST", path="items"),
            expect=Expect(
                response=[
                    Assertion(check="success"),
                    Assertion(check="has", params={"field": "itemId"}),
                ],
            ),
        )],
    )


def test_backend_projection_green_against_local_demo_server(demo_server):
    config = DemoConfig(base_url=demo_server)
    res = backend.run(
        _scenario(),
        auth=DemoAuthenticator(),
        api=DemoApiDriver(config),
        state=None,
        recorder=InMemoryRecorder(),
        resolve_request=resolve_request,
        normalizer=DemoResponseNormalizer(),
    )

    failures = [c for c in res.checks if not c.ok]
    assert res.passed, failures
    assert any(c.check == "success" and c.ok for c in res.checks)
    assert any(c.check == "has" and c.ok for c in res.checks)
    # no backend_state declared -> nothing skipped, nothing checked for it
    assert res.skipped == []
