import pytest

from refracto import ports
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import Assertion, Expect, Grid, Input, RequestTemplate, Scenario, Step, ValueRef
from refracto.projection import frontend
from refracto.report import DEGRADED
from tests.fakes import FakeNormalizer, FakeUi


def _rendered(identified=None, anonymous=None, anchor="result_row"):
    return {
        anchor: {
            "identified": list(identified or []),
            "anonymous": list(anonymous or []),
        },
    }


def _identified(object_id="42", **fields):
    return {"id": object_id, "fields": fields}


def _object_equals(*, value, source="input", key="item_id"):
    return Assertion(
        check="object_field_equals",
        params={
            "anchor": "result_row",
            "id": ValueRef(source=source, key=key),
            "field": "state",
            "value": value,
        },
    )


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
    ui = FakeUi(rendered=_rendered([
                    _identified("1"),
                    _identified("2"),
                ]),
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert res.passed
    assert len(res.steps) == 1
    assert res.steps[0].step_id == s.steps[0].id
    assert res.steps[0].status == res.status
    assert res.steps[0].resolved_bindings == {}
    assert any(c.check == "visible" and c.ok for c in res.checks)
    assert any(c.check == "count_gt" and c.ok for c in res.checks)
    assert any(c.point == "request" and c.ok for c in res.checks)


def test_frontend_visible_check_fails_when_no_objects_rendered():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered(),
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert any(c.check == "visible" and not c.ok for c in res.checks)


def test_frontend_count_check_fails_when_zero():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered(),
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert any(c.check == "count_gt" and not c.ok for c in res.checks)


def test_visible_and_count_include_identified_and_anonymous_objects():
    rendered = _rendered(
        [_identified("42")],
        anonymous=[{"fields": {}}, {"fields": {}}],
    )

    visible = frontend._eval_frontend(
        Assertion(check="visible", params={"anchor": "result_row"}),
        rendered,
    )
    count = frontend._eval_frontend(
        Assertion(check="count_gt", params={"anchor": "result_row", "n": 2}),
        rendered,
    )

    assert visible.ok
    assert count.ok


def test_frontend_fails_when_expected_request_not_sent():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered([_identified("1"), _identified("2")]), outgoing=[])
    res = frontend.run(s, ui=ui, normalizer=FakeNormalizer())
    assert not res.passed
    assert any(c.point == "request" and not c.ok for c in res.checks)


def test_object_field_equals_passes_for_matching_identified_object():
    check = frontend._eval_frontend(
        _object_equals(value="ready"),
        _rendered([_identified(state="ready")]),
        inputs=[Input(kind="item_id", value="42")],
    )

    assert check.ok


def test_object_field_equals_reports_expected_and_observed_on_value_drift():
    check = frontend._eval_frontend(
        _object_equals(value="ready"),
        _rendered([_identified(state="running")]),
        inputs=[Input(kind="item_id", value="42")],
    )

    assert not check.ok
    assert "id='42'" in check.detail
    assert "field='state'" in check.detail
    assert "expected='ready'" in check.detail
    assert "observed='running'" in check.detail


def test_object_field_equals_fails_when_identified_object_is_missing():
    check = frontend._eval_frontend(
        _object_equals(value="ready"),
        _rendered([_identified("41", state="ready")]),
        inputs=[Input(kind="item_id", value="42")],
    )

    assert not check.ok
    assert "no identified object" in check.detail
    assert "id='42'" in check.detail


def test_object_field_equals_resolves_from_bind_and_fails_unresolved_reference():
    assertion = _object_equals(value="ready", source="bind", key="item_id")
    rendered = _rendered([_identified(state="ready")])

    resolved = frontend._eval_frontend(
        assertion, rendered, bound_values={"item_id": "42"})
    unresolved = frontend._eval_frontend(assertion, rendered)

    assert resolved.ok
    assert not unresolved.ok
    assert "from_bind:item_id has no resolved bound value" in unresolved.detail


@pytest.mark.parametrize("observed, expected", [(True, 1), (3, 3.0)])
def test_object_field_equals_is_type_strict(observed, expected):
    check = frontend._eval_frontend(
        _object_equals(value=expected),
        _rendered([_identified(state=observed)]),
        inputs=[Input(kind="item_id", value="42")],
    )

    assert not check.ok
    assert f"expected={expected!r}" in check.detail
    assert f"observed={observed!r}" in check.detail


def test_no_anonymous_passes_when_empty_and_reports_nonempty_count():
    assertion = Assertion(check="no_anonymous", params={"anchor": "result_row"})

    clean = frontend._eval_frontend(
        assertion, _rendered([_identified(state="ready")]))
    dirty = frontend._eval_frontend(
        assertion,
        _rendered(
            [_identified(state="ready")],
            anonymous=[{"fields": {"state": "ghost"}}, {"fields": {}}],
        ),
    )

    assert clean.ok
    assert not dirty.ok
    assert "2 anonymous" in dirty.detail


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
