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


def _plan(payload=None):
    return [ports.MockResponse(fixture_id="import", source="explicit test fixture",
        method="POST", path="resource/action",
        response=payload if payload is not None else {"success": True, "data": {"taskId": "T1"}})]


def _run_frontend(scenario, *, ui, normalizer, **kwargs):
    return frontend.run(scenario, ui=ui, normalizer=normalizer, mock_plan=kwargs.pop("mock_plan", _plan()), **kwargs)


def test_frontend_consumes_explicit_fixture_not_consumer_synthesis():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered([_identified("1")]),
                outgoing=[ports.RequestSpec("POST", "resource/action")])
    result = _run_frontend(s, ui=ui, normalizer=FakeNormalizer())
    assert result.passed
    assert result.mock_consumption[0]["fixture_id"] == "import"
    assert result.mock_consumption[0]["source"] == "explicit test fixture"
    assert result.provider_recordings == []


def test_frontend_does_not_make_fixture_match_declared_parameter(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(
        "schema_version: 1\nscenario: x\nactor: a\nparameters: {rows: 3}\n"
        "steps:\n- id: read\n  do: click\n  target: resource.submit\n"
        "  expect:\n    request: {method: POST, path: [resource, action]}\n"
        "    response:\n"
        "      - {check: field_equals, field: count, value: {from_parameter: rows}}\n",
        encoding="utf-8")
    fixture = _plan({"success": True, "data": {"count": 4}})
    result = _run_frontend(load_scenario(str(y)),
        ui=FakeUi(outgoing=[ports.RequestSpec("POST", "resource/action")]),
        normalizer=FakeNormalizer(), mock_plan=fixture)
    assert not result.passed
    assert any(c.check == "field_equals" and not c.ok for c in result.checks)
    assert fixture[0].response["data"]["count"] == 4


def test_frontend_never_calls_normalizer_synthesis():
    class NormalizerWithoutSynthesis(FakeNormalizer):
        def synthesize(self, *args):
            raise AssertionError("Expectations must not generate mock responses")

    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    result = _run_frontend(scenario, ui=FakeUi(
        rendered=_rendered([_identified("1")]), outgoing=[ports.RequestSpec("POST", "resource/action")]),
        normalizer=NormalizerWithoutSynthesis())
    assert result.passed


def test_frontend_requires_explicit_mock_plan_before_any_context():
    scenario = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi()
    result = frontend.run(scenario, ui=ui, normalizer=FakeNormalizer())
    assert result.steps[0].status == "ERROR"
    assert "explicit mock_plan" in result.steps[0].detail
    assert ui.open_calls == 0 and ui.permits == []


def test_frontend_all_green():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered([
                    _identified("1"),
                    _identified("2"),
                ]),
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = _run_frontend(s, ui=ui, normalizer=FakeNormalizer())
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
    res = _run_frontend(s, ui=ui, normalizer=FakeNormalizer())
    assert any(c.check == "visible" and not c.ok for c in res.checks)


def test_frontend_count_check_fails_when_zero():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered(),
                outgoing=[ports.RequestSpec(method="POST", path="resource/action")])
    res = _run_frontend(s, ui=ui, normalizer=FakeNormalizer())
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
        Assertion(check="count_gt", params={"anchor": "result_row", "count": 2}),
        rendered,
    )

    assert visible.ok
    assert count.ok


def test_frontend_fails_when_expected_request_not_sent():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    ui = FakeUi(rendered=_rendered([_identified("1"), _identified("2")]), outgoing=[])
    res = _run_frontend(s, ui=ui, normalizer=FakeNormalizer())
    assert not res.passed
    assert res.steps[0].status == "ERROR"
    assert "missing or ambiguous" in res.steps[0].detail


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
    assert "response reference 'item_id' has no resolved value" in unresolved.detail


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


def test_frontend_missing_primitive_capability_is_explicit_before_actions():
    s = Scenario(
        id="test_missing_ui", grid=Grid("integration", "dataset"), actor="admin",
        precondition=[], inputs=[], intent="Primitive capability is required",
        steps=[
            Step(id="s1", request=RequestTemplate(method="POST", path="resource/action"),
                 action="click", target="submit", request_asserted=True,
                 expect=Expect(response=[Assertion("success", {})])),
            Step(id="s2", request=RequestTemplate(method="POST", path="resource/other"),
                 action="click", target="submit", request_asserted=True,
                 expect=Expect(response=[Assertion("success", {})])),
        ],
    )
    res = _run_frontend(s, ui=ports.UiDriver(), normalizer=FakeNormalizer())
    assert [step.status for step in res.steps] == ["ERROR", "BLOCKED"]
    assert "primitive UI capability not supported" in res.steps[0].detail
    assert not res.passed
