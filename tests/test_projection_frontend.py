import pytest

from refracto import ports
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import Assertion, Expect, Grid, RequestTemplate, Scenario, Step, ValueRef
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


def test_build_mock_synthesizes_declared_literal_and_input_values(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "inputs: [{rows: 3}]\n"
        "expect:\n"
        "  request:\n    - {check: request, method: GET, path: result}\n"
        "  response:\n"
        "    - {check: field_equals, field: state, value: ready}\n"
        "    - {check: field_equals, field: count, value: {from_input: rows}}\n",
        encoding="utf-8")

    mock = frontend.build_mock(load_scenario(str(y)), FakeNormalizer())

    assert mock[("GET", "result")]["data"] == {"state": "ready", "count": 3}


def test_build_mock_keeps_one_argument_normalizer_compatibility():
    class ExistingAdapterNormalizer(FakeNormalizer):
        def synthesize(self, fields):
            return super().synthesize(fields)

    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")

    mock = frontend.build_mock(scenario, ExistingAdapterNormalizer())

    assert "taskId" in mock[("POST", "resource/action")]["data"]


def test_build_mock_rejects_unresolvable_value_reference_as_declaration_error():
    """Direct model construction can bypass loader validation; mock synthesis
    must still classify an unresolved reference as a declaration problem."""
    scenario = Scenario(
        id="invalid_frontend_reference",
        grid=Grid("smoke", "generic"),
        actor="actor1",
        precondition=[],
        inputs=[],
        intent="",
        steps=[Step(
            id="main",
            request=RequestTemplate(method="GET", path="resource"),
            expect=Expect(response=[Assertion(
                check="field_equals",
                params={
                    "field": "itemId",
                    "value": ValueRef(source="bind", key="itemId"),
                },
            )]),
        )],
    )

    with pytest.raises(DeclarationError, match="from_bind:itemId"):
        frontend.build_mock(scenario, FakeNormalizer())


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
