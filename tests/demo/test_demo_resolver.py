"""End-to-end resolver validation through the backend projection. A real precondition creates an item, `resolve_request` fills `items/{id}` from the stored `itemId`, the scenario performs an update, and the resulting spans satisfy the declared backend assertions."""
from refracto.declaration.model import (
    Assertion, Expect, Grid, Input, Ref, RequestTemplate, Scenario, Step,
)
from refracto.projection import backend

from adapters.demo.wiring import build_adapters


def _update_scenario() -> Scenario:
    return Scenario(
        id="demo_item_update_resolver_inline",
        grid=Grid(level="regression", module="demo"),
        actor="user",
        precondition=[Ref(ref="item_exists")],
        inputs=[Input(kind="new_name", value="renamed")],
        intent="update an existing item's name",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="PUT", path="items"),
            expect=Expect(
                response=[Assertion(check="success"), Assertion(check="has", params={"field": "itemId"})],
                backend_state=[
                    Assertion(check="span_exists", params={"span": "item.update"}),
                    Assertion(check="span_attr",
                              params={"span": "item.update", "attr": "row_count", "op": ">", "value": 0}),
                ],
            ),
        )],
    )


def test_resolver_precondition_and_put_resolution_green(demo_server):
    adapters = build_adapters(demo_server)
    res = backend.run(
        _update_scenario(),
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
