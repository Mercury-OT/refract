"""Explicit fixtures for primitive UI protocol tests, independent of expectations."""
import copy
from refracto import ports
from refracto.declaration.model import Assertion, Binding, Expect, RequestTemplate, Scenario, Step, ValueRef
from refracto.projection import frontend, e2e
from tests.fakes import FakeAuth, FakeNormalizer, FakeRecorder, FakeUi


def rendered(value="alpha"):
    return {"rows": {"identified": [{"id": "1", "fields": {"name": value}}], "anonymous": []}}


def response(data=None):
    return {"success": True, "data": data if data is not None else {"id": "1", "name": "alpha"}}


def scenario(*, count=2, references=False, state=False):
    steps = []
    for i in range(count):
        request = RequestTemplate("POST", "items", {"name": "alpha"})
        expect = Expect(frontend=[Assertion("visible", {"anchor": "rows"})],
                        response=[Assertion("success"), Assertion("has", {"field": "id"})],
                        backend_state=[Assertion("span_exists", {"span": "created"})] if state else [])
        step = Step(f"s{i}", request, expect, action="click", target="submit", request_asserted=True)
        if references and i:
            step.bind = [Binding("previous", "s0", "id")]
            step.value = ValueRef("bind", "previous")
        steps.append(step)
    return Scenario("test.primitives", None, "editor", [], [], "Test explicit actions", steps)


class ScriptedUi(FakeUi):
    def __init__(self, count=2, *, payloads=None, requests=None, renders=None, mutate=None, terminal=None):
        super().__init__()
        self.payloads = payloads or [response({"id": str(i + 1), "name": "alpha"}) for i in range(count)]
        self.requests = requests or [[ports.RequestSpec("POST", "items", {"name": "alpha"})] for _ in range(count)]
        self.renders = renders or [rendered() for _ in range(count)]
        self.mutate = mutate
        self.terminal = terminal
        self.evidence = []

    def perform_step(self, scenario, step, context, permit):
        index = len(self.permits)
        if self.terminal == (index, "error"):
            self.permits.append(permit)
            raise RuntimeError("adapter error")
        if self.terminal == (index, "skip"):
            self.permits.append(permit)
            return ports.UiActionResult(skip_reason="explicit unavailable")
        self._outgoing = self.requests[index]
        self._recorded = [ports.RecordedResponse(200, {}, copy.deepcopy(self.payloads[index]), "", None, r)
                          for r in self._outgoing]
        self._rendered = self.renders[index]
        result = super().perform_step(scenario, step, context, permit)
        if self.mutate:
            result = self.mutate(index, result, permit)
        self.evidence.append(result)
        return result

    def plan(self):
        return [ports.MockResponse(fixture_id=f"f{i}-{j}", source="test fixture",
                                   method=r.method, path=r.path, response=copy.deepcopy(self.payloads[i]))
                for i, requests in enumerate(self.requests) for j, r in enumerate(requests)]


def run(s, ui, *, mode="live", **kwargs):
    if mode == "mock":
        return frontend.run(s, ui=ui, normalizer=kwargs.pop("normalizer", FakeNormalizer()),
                            auth=kwargs.pop("auth", FakeAuth()), mock_plan=kwargs.pop("mock_plan", ui.plan()),
                            **kwargs)
    return e2e.run(s, ui=ui, auth=kwargs.pop("auth", FakeAuth()),
                   normalizer=kwargs.pop("normalizer", FakeNormalizer()),
                   recorder=kwargs.pop("recorder", FakeRecorder()),
                   state=kwargs.pop("state", None), **kwargs)
