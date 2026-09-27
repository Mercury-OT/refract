import pytest

from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import (
    Assertion, Expect, Grid, Input, RequestTemplate, Scenario, Step, ValueRef,
)
from refracto.projection import e2e, frontend
from tests.fakes import FakeAuth, FakeNormalizer, FakeRecorder, FakeUi


def _rendered(identified=None, anonymous=None, anchor="project_row"):
    return {
        anchor: {
            "identified": list(identified or []),
            "anonymous": list(anonymous or []),
        },
    }


def _identified(object_id="1", **fields):
    return {"id": object_id, "fields": fields}


def _matching(n, value="active", *, source=None, key=None):
    if source is not None:
        value = ValueRef(source=source, key=key)
    return Assertion(
        check="objects_matching_count",
        params={"anchor": "project_row", "field": "status", "value": value, "n": n},
    )


def test_objects_matching_count_includes_identified_and_anonymous_and_is_order_independent():
    objects = [
        _identified("a", status="active"),
        {"fields": {"status": "active"}},
        _identified("b", status="paused"),
        {"fields": {"status": "active"}},
        {"fields": {"other": "active"}},
    ]
    assertion = _matching(3)

    first = frontend._eval_frontend(assertion, _rendered(objects[:1], objects[1:]))
    second = frontend._eval_frontend(
        assertion,
        _rendered(
            [objects[3], objects[0], objects[2]],
            [objects[4], objects[1]],
        ),
    )

    assert first.ok and second.ok


@pytest.mark.parametrize(
    "statuses, expected",
    [([], 0), (["active"], 1), (["active", "active", "paused"], 2)],
)
def test_objects_matching_count_passes_for_zero_one_and_many_matches(statuses, expected):
    rendered = _rendered([_identified(str(i), status=status) for i, status in enumerate(statuses)])
    assert frontend._eval_frontend(_matching(expected), rendered).ok


@pytest.mark.parametrize("expected, ok", [(0, False), (1, False), (2, True), (3, False), (4, False)])
def test_objects_matching_count_requires_exact_count(expected, ok):
    rendered = _rendered(
        [_identified("1", status="active"), _identified("2", status="active")],
        [{"fields": {"status": "paused"}}],
    )
    result = frontend._eval_frontend(_matching(expected), rendered)
    assert result.ok is ok
    if not ok:
        assert "matched 2" in result.detail


@pytest.mark.parametrize("observed, expected", [(False, False), (True, True)])
def test_objects_matching_count_uses_strict_value_equality(observed, expected):
    result = frontend._eval_frontend(
        _matching(1, value=expected),
        _rendered([_identified(status=observed)]),
    )
    assert result.ok


@pytest.mark.parametrize(
    "observed, expected",
    [
        # These direct counterexamples distinguish strict equality from `==`.
        (False, 0),
        (True, 1),
        (False, 1),
        (True, 0),
        (0, 1),
        (1, 0),
    ],
)
def test_objects_matching_count_rejects_bool_integer_confusion(observed, expected):
    result = frontend._eval_frontend(
        _matching(1, value=expected),
        _rendered([_identified(status=observed)]),
    )
    assert not result.ok


def test_objects_matching_count_resolves_input_bind_and_reports_unresolved():
    input_result = frontend._eval_frontend(
        _matching(1, source="input", key="wanted"),
        _rendered([_identified(status="active")]),
        inputs=[Input(kind="wanted", value="active")],
    )
    bind_result = frontend._eval_frontend(
        _matching(1, source="bind", key="wanted"),
        _rendered([_identified(status="active")]),
        bound_values={"wanted": "active"},
    )
    unresolved = frontend._eval_frontend(
        _matching(0, source="bind", key="wanted"),
        _rendered(),
    )

    assert input_result.ok and bind_result.ok
    assert not unresolved.ok
    assert "from_bind:wanted has no resolved bound value" in unresolved.detail


def test_frontend_and_e2e_use_the_same_matching_count_evaluator():
    scenario = Scenario(
        id="matching_count_parity",
        grid=Grid("smoke", "generic"),
        actor="viewer",
        precondition=[],
        inputs=[],
        intent="",
        steps=[Step(
            id="main",
            request=None,
            expect=Expect(frontend=[_matching(2)]),
        )],
    )
    rendered = _rendered(
        [_identified("1", status="active")],
        [{"fields": {"status": "active"}}],
    )
    frontend_result = frontend.run(
        scenario,
        ui=FakeUi(rendered=rendered),
        normalizer=FakeNormalizer(),
    )
    e2e_result = e2e.run(
        scenario,
        auth=FakeAuth(),
        ui=FakeUi(rendered=rendered),
        state=None,
        recorder=FakeRecorder(),
        normalizer=FakeNormalizer(),
    )

    assert frontend_result.passed and e2e_result.passed
    assert [(c.check, c.ok, c.detail) for c in frontend_result.checks] == [
        (c.check, c.ok, c.detail) for c in e2e_result.checks
    ]


def _scenario_text(frontend_assertion, *, inputs="", steps=None):
    if steps is not None:
        return (
            "version: 2\nscenario: demo.matching_count\n"
            "grid: {level: smoke, module: ui}\nactor: viewer\n"
            f"inputs: {inputs}\nsteps:\n" + steps
        )
    return (
        "scenario: demo.matching_count\ngrid: {level: smoke, module: ui}\n"
        "actor: viewer\n" + f"inputs: {inputs}\n"
        "expect:\n  frontend:\n    - " + frontend_assertion + "\n"
    )


def _load_text(tmp_path, text):
    path = tmp_path / "scenario.yaml"
    path.write_text(text, encoding="utf-8")
    return load_scenario(str(path))


def test_loader_accepts_literal_and_input_references(tmp_path):
    literal = _load_text(
        tmp_path,
        _scenario_text(
            "{check: objects_matching_count, anchor: project_row, field: status, value: active, n: 1}",
            inputs="[]",
        ),
    )
    input_ref = _load_text(
        tmp_path,
        _scenario_text(
            "{check: objects_matching_count, anchor: project_row, field: status, "
            "value: {from_input: wanted}, n: 1}",
            inputs="[{wanted: active}]",
        ),
    )
    assert literal.steps[0].expect.frontend[0].params["value"] == "active"
    assert isinstance(input_ref.steps[0].expect.frontend[0].params["value"], ValueRef)


def test_loader_accepts_from_bind_and_counts_it_as_used(tmp_path):
    text = _scenario_text(
        "unused",
        inputs="[]",
        steps=(
            "  - id: create\n"
            "    request: {method: POST, path: projects}\n"
            "    expect:\n"
            "      response:\n"
            "        - {check: has, field: status}\n"
            "  - id: list\n"
            '    request: {method: GET, path: "projects/{wanted}"}\n'
            "    bind: {wanted: {from: create, field: status}}\n"
            "    expect:\n"
            "      frontend:\n"
            "        - {check: objects_matching_count, anchor: project_row, field: status, "
            "value: {from_bind: wanted}, n: 1}\n"
        ),
    )
    scenario = _load_text(tmp_path, text)
    assert isinstance(
        scenario.steps[1].expect.frontend[0].params["value"], ValueRef)


@pytest.mark.parametrize(
    "fragment",
    [
        "anchor: '', field: status, value: active, n: 1",
        "anchor: 1, field: status, value: active, n: 1",
        "anchor: [], field: status, value: active, n: 1",
        "anchor: project_row, field: '', value: active, n: 1",
        "anchor: project_row, field: 1, value: active, n: 1",
        "anchor: project_row, field: [], value: active, n: 1",
        "anchor: project_row, field: status, value: active, n: true",
        "anchor: project_row, field: status, value: active, n: 1.0",
        "anchor: project_row, field: status, value: active, n: -1",
        "anchor: project_row, field: status, value: [active], n: 1",
        "anchor: project_row, field: status, value: {nested: active}, n: 1",
        "anchor: project_row, field: status, value: active, n: 1, extra: nope",
    ],
)
def test_loader_rejects_invalid_objects_matching_count_params(tmp_path, fragment):
    text = (
        "scenario: demo.matching_count\ngrid: {level: smoke, module: ui}\n"
        "actor: viewer\nexpect:\n  frontend:\n    - {check: objects_matching_count, "
        + fragment
        + "}\n"
    )
    with pytest.raises(DeclarationError):
        _load_text(tmp_path, text)


def test_loader_rejects_unresolved_bind_reference(tmp_path):
    text = _scenario_text(
        "{check: objects_matching_count, value: {from_bind: wanted}, "
        "anchor: project_row, field: status, n: 0}",
        inputs="[]",
    )
    with pytest.raises(DeclarationError, match="from_bind.*wanted"):
        _load_text(tmp_path, text)
