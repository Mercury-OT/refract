"""Mandatory real Chromium live proof; browser absence is a failure, not a skip."""
from adapters.demo.config import DemoConfig
from adapters.demo.ui import DemoUiDriver
from adapters.demo.wiring import build_adapters
from refracto.runner import run_scenario


class ObservedDemoUiDriver(DemoUiDriver):
    def __init__(self, config):
        super().__init__(config)
        self.open_calls = self.close_calls = 0
        self.contexts, self.permits, self.results = [], [], []

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None):
        self.open_calls += 1
        context = super().open_stepwise(scenario, session, mode=mode, mock_plan=mock_plan)
        self.contexts.append(context)
        return context

    def perform_step(self, scenario, step, context, permit):
        self.contexts.append(context)
        self.permits.append(permit)
        result = super().perform_step(scenario, step, context, permit)
        self.results.append(result)
        return result

    def close_stepwise(self, context):
        self.close_calls += 1
        super().close_stepwise(context)


def test_demo_live_two_step_e2e_is_strictly_correlated(demo_server):
    driver = ObservedDemoUiDriver(DemoConfig(base_url=demo_server))
    report = run_scenario("scenarios/demo_item_e2e_stepwise.yaml",
        build_adapters(demo_server, ui=driver), projections=("e2e",))
    domain = report.domains[0]
    assert report.status == "PASSED", [(s.status, s.detail) for s in domain.steps]
    assert report.degradations() == []
    assert driver.open_calls == driver.close_calls == 1
    assert len(driver.permits) == 6
    assert all(c is driver.contexts[0] for c in driver.contexts)
    assert [p.action for p in driver.permits] == ["open", "click", "fill", "click", "fill", "click"]
    assert len({p.action_id for p in driver.permits}) == 6
    assert len(domain.provider_recordings) == 2
    assert [r.step_id for r in domain.provider_recordings] == ["create_first", "create_second"]
    assert [r.json["data"]["itemKey"] for r in domain.provider_recordings] == ["1", "2"]
    assert len({r.trace_id for r in domain.provider_recordings}) == 2
    assert all({c.point for c in s.checks} == {"frontend", "request", "response", "backend_state"}
               for s in (domain.steps[3], domain.steps[5]))
    diagnostics = [r for result in driver.results for r in result.evidence.diagnostic_recorded]
    assert diagnostics and all(r.request.method == "GET" for r in diagnostics)
    assert not any(r.request.method == "GET" for r in domain.provider_recordings)
