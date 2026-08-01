from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Assertion, Expect, Grid, RequestTemplate, Scenario, Step
from refracto.projection import frontend
from refracto.report import DEGRADED
from tests.fakes import FakeNormalizer, FakeUi


def test_build_mock_from_consumer_contract():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    mock = frontend.build_mock(s, FakeNormalizer())
    key = ("POST", "resource/action")
    assert key in mock
    assert mock[key]["success"] is True
    assert "taskId" in mock[key]["data"]


def test_frontend_all_green():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered={"result_row": {"visible": True, "count": 2}},
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert res.passed
    assert len(res.steps) == 1
    assert res.steps[0].step_id == s.steps[0].id
    assert res.steps[0].status == res.status
    assert any(c.check == "visible" and c.ok for c in res.checks)
    assert any(c.check == "count_gt" and c.ok for c in res.checks)
    assert any(c.point == "request" and c.ok for c in res.checks)


def test_frontend_visible_check_fails_when_hidden():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered={"result_row": {"visible": False, "count": 2}},
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert any(c.check == "visible" and not c.ok for c in res.checks)
    assert all(c.ok for c in res.checks if c.check != "visible")


def test_frontend_count_check_fails_when_zero():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered={"result_row": {"visible": True, "count": 0}},
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert any(c.check == "count_gt" and not c.ok for c in res.checks)
    assert all(c.ok for c in res.checks if c.check != "count_gt")


def test_frontend_fails_when_expected_request_not_sent():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered={"result_row": {"visible": True, "count": 2}}, outgoing=[])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert not res.passed
    assert any(c.point == "request" and not c.ok for c in res.checks)


def test_frontend_multi_step_unsupported_degrades():
    s = Scenario(
        id="test_multi_step_ui",
        grid=Grid("integration", "dataset"),
        actor="admin",
        precondition=[],
        inputs=[],
        intent="multi-step UI is not supported in the frontend projection",
        steps=[
            Step(id="s1", request=RequestTemplate(method="POST", path="resource/action"),
                 expect=Expect(response=[Assertion("success", {})])),
            Step(id="s2", request=RequestTemplate(method="POST", path="resource/other"),
                 expect=Expect(response=[Assertion("success", {})])),
        ],
    )
    res = frontend.run(s, ui=FakeUi(), normalizer=FakeNormalizer())
    assert res.steps == []
    assert res.skipped == ["multi-step UI not supported"]
    assert res.status == DEGRADED
