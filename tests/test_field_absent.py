import copy
import types

import pytest

from refracto import ports
from refracto.contract import store
from refracto.declaration import vocabulary
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import (
    Assertion,
    Expect,
    Grid,
    RequestTemplate,
    Scenario,
    Step,
)
from refracto.projection import backend, contract as contract_projection, e2e
from refracto.report import FAILED, PASSED, SKIPPED
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder, FakeUi


def _write(tmp_path, text):
    path = tmp_path / "scenario.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _v1_response(*assertions):
    lines = "\n".join(f"    - {assertion}" for assertion in assertions)
    return (
        "scenario: field_absent\n"
        "grid: {level: regression, module: generic}\n"
        "actor: actor\n"
        "expect:\n"
        "  request:\n"
        "    - {check: request, method: GET, path: resource}\n"
        "  response:\n"
        f"{lines}\n"
    )


def _field_absent_scenario():
    return Scenario(
        id="field_absent",
        grid=Grid("regression", "generic"),
        actor="actor",
        precondition=[],
        inputs=[],
        intent="exclude an internal field from the normalized response",
        steps=[Step(
            id="main",
            request=RequestTemplate("GET", "resource"),
            expect=Expect(response=[Assertion(
                "field_absent", {"field": "internal_token"}
            )]),
        )],
    )


def _resolver(scenario, step, template):
    return ports.RequestSpec(
        method=template.method,
        path=template.path,
        body=template.body or {},
    )


def _recording(fields, *, value_json=None):
    spec = ports.RequestSpec(method="GET", path="resource")
    body = value_json
    if body is None:
        body = {"success": True, "data": dict(fields)}
    return ports.RecordedResponse(
        status=200,
        headers={},
        json=body,
        text="",
        trace_id=None,
        request=spec,
        step_id="main",
        template_path="resource",
    )


def test_field_absent_vocabulary_has_one_bounded_parameter():
    assert vocabulary.is_valid("response", "field_absent")
    assert vocabulary.required_params("response", "field_absent") == ("field",)
    assert vocabulary.optional_params("response", "field_absent") == ()


@pytest.mark.parametrize(
    "scenario_text",
    [
        _v1_response("{check: field_absent, field: internal_token}"),
        (
            "version: 2\n"
            "scenario: field_absent\n"
            "grid: {level: regression, module: generic}\n"
            "actor: actor\n"
            "steps:\n"
            "  - id: read\n"
            "    request: {method: GET, path: resource}\n"
            "    expect:\n"
            "      response:\n"
            "        - {check: field_absent, field: internal_token}\n"
        ),
    ],
)
def test_loader_accepts_field_absent_in_v1_and_v2(tmp_path, scenario_text):
    scenario = load_scenario(str(_write(tmp_path, scenario_text)))

    assertion = scenario.steps[0].expect.response[0]
    assert assertion.check == "field_absent"
    assert assertion.params == {"field": "internal_token"}


@pytest.mark.parametrize(
    "assertion",
    [
        "{check: field_absent, field: ''}",
        "{check: field_absent, field: [internal_token]}",
        "{check: field_absent, field: internal_token, value: secret}",
    ],
)
def test_loader_rejects_invalid_field_absent_parameters(tmp_path, assertion):
    with pytest.raises(DeclarationError):
        load_scenario(str(_write(tmp_path, _v1_response(assertion))))


@pytest.mark.parametrize(
    "assertions",
    [
        (
            "{check: field_absent, field: internal_token}",
            "{check: field_absent, field: internal_token}",
        ),
        (
            "{check: field_absent, field: internal_token}",
            "{check: has, field: internal_token}",
        ),
        (
            "{check: field_absent, field: internal_token}",
            "{check: field_equals, field: internal_token, value: expected}",
        ),
    ],
)
def test_loader_rejects_duplicate_and_positive_negative_field_conflicts(
    tmp_path, assertions
):
    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(_write(tmp_path, _v1_response(*assertions))))

    assert "field_absent" in str(exc_info.value)


def test_existing_has_and_field_equals_combination_remains_legal(tmp_path):
    scenario = load_scenario(str(_write(
        tmp_path,
        _v1_response(
            "{check: has, field: state}",
            "{check: field_equals, field: state, value: ready}",
        ),
    )))

    assert [a.check for a in scenario.steps[0].expect.response] == [
        "has",
        "field_equals",
    ]


def test_v1_async_implicit_has_participates_in_conflict_check(tmp_path):
    text = (
        "scenario: async_conflict\n"
        "grid: {level: regression, module: generic}\n"
        "actor: actor\n"
        "expect:\n"
        "  request:\n"
        "    - {check: request, method: POST, path: jobs, async: task_id}\n"
        "  response:\n"
        "    - {check: field_absent, field: task_id}\n"
    )

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(_write(tmp_path, text)))

    assert "field_absent" in str(exc_info.value)
    assert "task_id" in str(exc_info.value)


def test_field_absent_does_not_guarantee_a_later_binding_source(tmp_path):
    text = (
        "version: 2\n"
        "scenario: invalid_bind\n"
        "grid: {level: regression, module: generic}\n"
        "actor: actor\n"
        "steps:\n"
        "  - id: source\n"
        "    request: {method: GET, path: source}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: field_absent, field: item_id}\n"
        "  - id: target\n"
        "    request: {method: GET, path: 'items/{item_id}'}\n"
        "    bind: {item_id: {from: source, field: item_id}}\n"
    )

    with pytest.raises(DeclarationError) as exc_info:
        load_scenario(str(_write(tmp_path, text)))

    assert "not guaranteed by source step" in str(exc_info.value)


def test_backend_field_absent_passes_only_when_normalized_field_is_missing():
    assertion = Assertion("field_absent", {"field": "internal_token"})
    normalized = ports.NormalizedResponse(
        succeeded=True,
        fields={},
        status=200,
        raw=None,
    )

    check = backend._eval_response(assertion, normalized)

    assert check.ok is True
    assert check.detail == ""


@pytest.mark.parametrize("present_value", [None, 0, False, "", [], {}])
def test_backend_field_absent_fails_for_every_present_value_without_reporting_it(
    present_value,
):
    assertion = Assertion("field_absent", {"field": "internal_token"})
    normalized = ports.NormalizedResponse(
        succeeded=True,
        fields={"internal_token": present_value},
        status=200,
        raw=None,
    )

    check = backend._eval_response(assertion, normalized)

    assert check.ok is False
    assert check.detail == "unexpected field 'internal_token' present"


def test_backend_field_absent_detail_does_not_repeat_sensitive_value():
    sentinel = "sensitive-value-that-must-not-appear"
    assertion = Assertion("field_absent", {"field": "internal_token"})
    normalized = ports.NormalizedResponse(
        succeeded=True,
        fields={"internal_token": sentinel},
        status=200,
        raw=None,
    )

    check = backend._eval_response(assertion, normalized)

    assert check.ok is False
    assert sentinel not in check.detail


class FakeClock:
    def __init__(self):
        self.time = 0.0

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds


class SequenceApi(ports.ApiDriver):
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def send(self, spec, session):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        trace_id = spec.traceparent.split("-")[1]
        return ports.RecordedResponse(
            status=200,
            headers={},
            json=copy.deepcopy(response),
            text="",
            trace_id=trace_id,
            request=spec,
        )


def _poll_scenario(tmp_path, on_timeout):
    text = (
        "version: 2\n"
        "scenario: poll_absence\n"
        "grid: {level: regression, module: generic}\n"
        "actor: actor\n"
        "steps:\n"
        "  - id: poll\n"
        "    request: {method: GET, path: resource}\n"
        f"    poll: {{on_timeout: {on_timeout}}}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: field_absent, field: internal_token}\n"
    )
    return load_scenario(str(_write(tmp_path, text)))


def _run_poll(scenario, api):
    clock = FakeClock()
    return backend.run(
        scenario,
        auth=FakeAuth(),
        api=api,
        state=None,
        recorder=FakeRecorder(),
        resolve_request=_resolver,
        normalizer=FakeNormalizer(),
        poll_config=types.SimpleNamespace(timeout=2, interval=1),
        now=clock.now,
        sleep=clock.sleep,
    )


def test_poll_field_absent_passes_after_field_disappears(tmp_path):
    api = SequenceApi([
        {"success": True, "data": {"internal_token": "transient"}},
        {"success": True, "data": {}},
    ])

    result = _run_poll(_poll_scenario(tmp_path, "FAIL"), api)

    assert result.steps[0].status == PASSED
    assert result.steps[0].attempts == 2
    assert result.steps[0].checks[0].check == "field_absent"
    assert result.steps[0].checks[0].ok is True


@pytest.mark.parametrize(
    ("on_timeout", "expected_status"),
    [("FAIL", FAILED), ("SKIP", SKIPPED)],
)
def test_poll_field_absent_preserves_existing_timeout_outcomes(
    tmp_path, on_timeout, expected_status
):
    sentinel = "sensitive-value-that-must-not-appear"
    api = SequenceApi([
        {"success": True, "data": {"internal_token": sentinel}},
    ])

    result = _run_poll(_poll_scenario(tmp_path, on_timeout), api)

    assert result.steps[0].status == expected_status
    assert sentinel not in repr(result.steps[0].checks)


def test_e2e_field_absent_uses_normalized_fields_not_raw_json():
    sentinel = "raw-sensitive-value"
    raw_response = _recording(
        {},
        value_json={"success": True, "internal_token": sentinel},
    )
    ui = FakeUi(outgoing=[raw_response.request], recorded=[raw_response])

    class FilteringNormalizer(FakeNormalizer):
        def normalize(self, response):
            return ports.NormalizedResponse(
                succeeded=True,
                fields={},
                status=response.status,
                raw=response,
            )

    filtered = e2e.run(
        _field_absent_scenario(),
        auth=FakeAuth(),
        ui=ui,
        state=None,
        recorder=FakeRecorder(),
        normalizer=FilteringNormalizer(),
    )
    exposed = e2e.run(
        _field_absent_scenario(),
        auth=FakeAuth(),
        ui=ui,
        state=None,
        recorder=FakeRecorder(),
        normalizer=FakeNormalizer(),
    )

    assert filtered.status == PASSED
    assert exposed.status == FAILED
    failed = next(check for check in exposed.checks if check.check == "field_absent")
    assert failed.detail == "unexpected field 'internal_token' present"
    assert sentinel not in failed.detail


def test_contract_models_add_negative_sets_without_expanding_positional_api():
    shape = store.EndpointShape(
        frozenset({"public"}),
        {"public": 1},
        store.REQUIRES_SUCCESS,
        True,
    )
    mismatch = store.ContractMismatch(
        ("main", "GET", "resource"),
        frozenset(),
        "note",
        {},
        {},
    )

    assert shape.forbidden_fields == frozenset()
    assert mismatch.unexpected_fields == frozenset()
    assert "forbidden_fields" not in store.EndpointShape.__match_args__
    assert "unexpected_fields" not in store.ContractMismatch.__match_args__


def test_consumer_contract_records_forbidden_fields_separately():
    consumer = store.consumer_contract(_field_absent_scenario())
    shape = consumer.entries[("main", "GET", "resource")]

    assert shape.response_fields == frozenset()
    assert shape.response_values == {}
    assert shape.forbidden_fields == frozenset({"internal_token"})


def test_contract_passes_when_provider_normalized_field_is_missing():
    scenario = _field_absent_scenario()
    provider = store.provider_contract([_recording({})], FakeNormalizer())

    assert store.diff(store.consumer_contract(scenario), provider) == []
    assert contract_projection.run(
        scenario, [_recording({})], FakeNormalizer()
    ).status == PASSED


@pytest.mark.parametrize("present_value", [None, "sensitive-provider-value"])
def test_contract_reports_unexpected_field_without_its_value(present_value):
    scenario = _field_absent_scenario()
    recording = _recording({"internal_token": present_value})
    consumer = store.consumer_contract(scenario)
    provider = store.provider_contract([recording], FakeNormalizer())

    mismatches = store.diff(consumer, provider)
    result = contract_projection.run(scenario, [recording], FakeNormalizer())

    assert len(mismatches) == 1
    assert mismatches[0].unexpected_fields == frozenset({"internal_token"})
    assert present_value not in mismatches[0].unexpected_fields
    assert result.status == FAILED
    assert "internal_token" in result.checks[0].detail
    if isinstance(present_value, str):
        assert present_value not in repr(mismatches[0])
        assert present_value not in result.checks[0].detail


def test_forbidden_only_contract_still_fails_when_endpoint_was_not_observed():
    result = contract_projection.run(
        _field_absent_scenario(),
        [],
        FakeNormalizer(),
    )

    assert result.status == FAILED
    assert "endpoint not observed" in result.checks[0].detail
