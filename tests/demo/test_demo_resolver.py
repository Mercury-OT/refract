"""A resolver maps declared data without preparing hidden business state."""
from adapters.demo.wiring import build_adapters
from refracto import runner


def test_resolver_explicit_create_then_update_is_green(demo_server):
    report = runner.run_scenario("scenarios/demo_item_update.yaml", build_adapters(demo_server), projections=("backend",))
    assert report.status == "PASSED", report.localize()
    assert len(report.domains[0].steps) == 2
    assert any(c.check == "span_exists" and c.ok for c in report.domains[0].checks)
    assert any(c.check == "span_attr" and c.ok for c in report.domains[0].checks)
