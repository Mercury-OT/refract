"""The backend projection's Tier-3 story: backend_state assertions evaluated against a
real StateProbe, driven fully through adapters/demo/wiring.py::build_adapters — auth,
api, state and request-resolution all come from the demo adapter (not an inline
hand-built resolve_request). The scenario declares both response and backend_state
assertions; the bar is that nothing degrades to 'skipped' (state is wired) and
everything passes for real against the locally-started demo-app server."""
from refracto.declaration.model import Assertion, Expect, Grid, Input, RequestTemplate, Scenario, Step
from refracto.projection import backend

from adapters.demo.wiring import build_adapters


def _scenario() -> Scenario:
    return Scenario(
        id="demo_item_create_backend_state",
        grid=Grid(level="smoke", module="demo"),
        actor="tester",
        precondition=[],
        inputs=[Input(kind="rows", value=3)],
        intent="create an item via POST /items and observe its item.create span",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="POST", path="items"),
            expect=Expect(
                response=[
                    Assertion(check="success"),
                    Assertion(check="has", params={"field": "itemId"}),
                ],
                backend_state=[
                    Assertion(check="span_exists", params={"span": "item.create"}),
                    Assertion(check="span_attr",
                             params={"span": "item.create", "attr": "row_count", "op": ">", "value": 0}),
                ],
            ),
        )],
    )


def test_backend_state_projection_green_against_local_demo_server(demo_server):
    adapters = build_adapters(demo_server)
    res = backend.run(
        _scenario(),
        auth=adapters.auth,
        api=adapters.api,
        state=adapters.state,
        recorder=adapters.recorder_factory(),
        resolve_request=adapters.resolve_request,
        resolve_precondition=adapters.resolve_precondition,
        normalizer=adapters.normalizer,
    )

    failures = [c for c in res.checks if not c.ok]
    assert res.passed, failures
    assert all(not s.skipped for s in res.steps)
    assert any(c.check == "span_exists" and c.ok for c in res.checks)
    assert any(c.check == "span_attr" and c.ok for c in res.checks)
