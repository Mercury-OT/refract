from refracto import ports
from refracto.contract import store
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Assertion, Expect, Grid, RequestTemplate, Scenario, Step
from refracto.projection import contract as contract_proj
from refracto.report import FAILED, PASSED
from tests.fakes import FakeNormalizer


def _resp(method, path, status, data_fields, step_id=None, template_path=None, is_final=True):
    spec = ports.RequestSpec(method=method, path=path)
    return ports.RecordedResponse(
        status=status,
        headers={},
        text="",
        json={"success": True, "data": {k: 1 for k in data_fields}},
        trace_id=None,
        request=spec,
        step_id=step_id,
        template_path=template_path,
        is_final=is_final,
    )


def _scenario(steps):
    return Scenario(
        id="test.synthetic",
        grid=Grid(level="smoke", module="generic"),
        actor="actor1",
        precondition=[],
        inputs=[],
        intent="",
        steps=steps,
    )


def test_consumer_from_scenario():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    c = store.consumer_contract(s)
    key = ("main", "POST", "resource/action")
    assert key in c.entries
    assert c.entries[key].status_ok is True
    assert "taskId" in c.entries[key].response_fields


def test_consumer_contract_one_entry_per_step():
    step1 = Step(
        id="create",
        request=RequestTemplate(method="POST", path="resource/action"),
        expect=Expect(response=[Assertion(check="success"), Assertion(check="has", params={"field": "taskId"})]),
    )
    step2 = Step(
        id="verify",
        request=RequestTemplate(method="GET", path="resource/status"),
        expect=Expect(response=[Assertion(check="has", params={"field": "state"})]),
    )
    s = _scenario([step1, step2])
    c = store.consumer_contract(s)
    assert len(c.entries) == 2
    create = c.entries[("create", "POST", "resource/action")]
    assert create.status_ok is True
    assert "taskId" in create.response_fields
    verify = c.entries[("verify", "GET", "resource/status")]
    assert verify.status_ok is False
    assert "state" in verify.response_fields


def test_provider_from_recordings():
    recs = [_resp("POST", "resource/action", 200, ["taskId", "other"])]
    p = store.provider_contract(recs, FakeNormalizer())
    key = (None, "POST", "resource/action")
    assert p.entries[key].status_ok is True
    assert "taskId" in p.entries[key].response_fields


def test_diff_flags_missing_field():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    consumer = store.consumer_contract(s)
    provider = store.provider_contract(
        [_resp("POST", "resource/action", 200, ["somethingElse"], step_id="main", template_path="resource/action")],
        FakeNormalizer(),
    )
    mismatches = store.diff(consumer, provider)
    assert any("taskId" in m.missing_fields for m in mismatches)


def test_provider_fields_fall_back_to_top_level_keys():
    spec = ports.RequestSpec(method="GET", path="p")
    rec = ports.RecordedResponse(
        status=200,
        headers={},
        text="",
        json={"success": True, "uploadTaskId": "T1"},
        trace_id=None,
        request=spec,
    )
    p = store.provider_contract([rec], FakeNormalizer())
    assert "uploadTaskId" in p.entries[(None, "GET", "p")].response_fields


def test_diff_clean_when_provider_satisfies():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    consumer = store.consumer_contract(s)
    provider = store.provider_contract(
        [_resp("POST", "resource/action", 200, ["taskId"], step_id="main", template_path="resource/action")],
        FakeNormalizer(),
    )
    assert store.diff(consumer, provider) == []


def test_contract_run_templated_multi_step_clean_passes():
    static_step = Step(
        id="create",
        request=RequestTemplate(method="POST", path="resource/action"),
        expect=Expect(response=[
            Assertion(check="success"),
            Assertion(check="has", params={"field": "itemId"}),
        ]),
    )
    templated_step = Step(
        id="get_item",
        request=RequestTemplate(method="GET", path="items/{itemId}"),
        expect=Expect(response=[
            Assertion(check="success"),
            Assertion(check="has", params={"field": "name"}),
        ]),
    )
    s = _scenario([static_step, templated_step])
    recs = [
        _resp("POST", "/api/items", 200, ["itemId"],
              step_id="create", template_path="resource/action"),
        _resp("GET", "/api/items/42", 200, ["name"],
              step_id="get_item", template_path="items/{itemId}"),
    ]

    res = contract_proj.run(s, recs, FakeNormalizer())

    assert res.status == PASSED
    assert res.skipped == []
    assert res.checks[0].ok is True


def test_contract_run_templated_multi_step_drift_names_failing_step():
    static_step = Step(
        id="create",
        request=RequestTemplate(method="POST", path="resource/action"),
        expect=Expect(response=[Assertion(check="has", params={"field": "itemId"})]),
    )
    templated_step = Step(
        id="get_item",
        request=RequestTemplate(method="GET", path="items/{itemId}"),
        expect=Expect(response=[Assertion(check="has", params={"field": "name"})]),
    )
    s = _scenario([static_step, templated_step])
    recs = [
        _resp("POST", "/api/items", 200, ["itemId"],
              step_id="create", template_path="resource/action"),
        _resp("GET", "/api/items/42", 200, ["renamedField"],
              step_id="get_item", template_path="items/{itemId}"),
    ]

    res = contract_proj.run(s, recs, FakeNormalizer())

    assert res.status == FAILED
    assert len(res.checks) == 1
    assert res.checks[0].step == "get_item"
    assert "name" in res.checks[0].detail


def test_contract_run_static_only_clean_passes():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    rec = _resp("POST", "resource/action", 200, ["taskId"], step_id="main", template_path="resource/action")
    res = contract_proj.run(s, [rec], FakeNormalizer())
    assert len(res.steps) == 1
    assert res.steps[0].step_id == "contract"
    assert res.steps[0].status == PASSED
    assert res.status == PASSED


def test_contract_run_static_only_drift_fails():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    rec = _resp("POST", "resource/action", 200, ["renamedField"], step_id="main", template_path="resource/action")
    res = contract_proj.run(s, [rec], FakeNormalizer())
    assert len(res.steps) == 1
    assert res.steps[0].step_id == "contract"
    assert res.steps[0].status == FAILED
    assert res.status == FAILED
    assert any(not c.ok for c in res.checks)


def test_provider_matches_consumer_via_template_path_not_bound_path():
    step = Step(
        id="create_job",
        request=RequestTemplate(method="POST", path="jobs"),
        expect=Expect(response=[Assertion(check="success")]),
    )
    s = _scenario([step])
    consumer = store.consumer_contract(s)
    key = ("create_job", "POST", "jobs")
    assert key in consumer.entries

    rec = _resp("POST", "/api/v2/jobs", 200, [], step_id="create_job", template_path="jobs")
    provider = store.provider_contract([rec], FakeNormalizer())
    assert key in provider.entries
    assert store.diff(consumer, provider) == []


def test_two_steps_on_same_endpoint_produce_distinct_entries():
    step_a = Step(
        id="a",
        request=RequestTemplate(method="GET", path="resource"),
        expect=Expect(response=[Assertion(check="has", params={"field": "x"})]),
    )
    step_b = Step(
        id="b",
        request=RequestTemplate(method="GET", path="resource"),
        expect=Expect(response=[Assertion(check="has", params={"field": "y"})]),
    )
    s = _scenario([step_a, step_b])
    consumer = store.consumer_contract(s)
    assert len(consumer.entries) == 2
    assert ("a", "GET", "resource") in consumer.entries
    assert ("b", "GET", "resource") in consumer.entries
    assert "x" in consumer.entries[("a", "GET", "resource")].response_fields
    assert "y" in consumer.entries[("b", "GET", "resource")].response_fields

    rec_a = _resp("GET", "resource", 200, ["x"], step_id="a", template_path="resource")
    rec_b = _resp("GET", "resource", 200, ["y"], step_id="b", template_path="resource")
    provider = store.provider_contract([rec_a, rec_b], FakeNormalizer())
    assert len(provider.entries) == 2
    assert "x" in provider.entries[("a", "GET", "resource")].response_fields
    assert "y" in provider.entries[("b", "GET", "resource")].response_fields
    assert store.diff(consumer, provider) == []


def test_provider_ignores_non_final_recordings():
    pending = _resp("GET", "poll", 200, [], step_id="poll_step", template_path="poll", is_final=False)
    final = _resp("GET", "poll", 200, ["result"], step_id="poll_step", template_path="poll", is_final=True)

    provider_pending_only = store.provider_contract([pending], FakeNormalizer())
    assert provider_pending_only.entries == {}

    provider = store.provider_contract([pending, final], FakeNormalizer())
    assert len(provider.entries) == 1
    key = ("poll_step", "GET", "poll")
    assert provider.entries[key].response_fields == frozenset({"result"})
