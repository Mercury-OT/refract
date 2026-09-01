import copy
import types

import pytest

from refracto import ports
from refracto.declaration.model import (
    Assertion,
    Binding,
    Expect,
    Grid,
    PollPolicy,
    RequestTemplate,
    Scenario,
    Step,
)
from refracto.projection import backend
from refracto.report import BLOCKED, ERROR, FAILED, PASSED, SKIPPED
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder


class FakeClock:
    def __init__(self):
        self.time = 0.0

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds


class SequencedApi(ports.ApiDriver):
    def __init__(self, sequences):
        self.sequences = sequences
        self.calls = {}
        self.sent = []

    def send(self, spec, session):
        key = (spec.method, spec.path)
        index = self.calls.get(key, 0)
        self.calls[key] = index + 1
        sequence = self.sequences[key]
        response = sequence[min(index, len(sequence) - 1)]
        self.sent.append(spec)
        trace_id = spec.traceparent.split("-")[1] if spec.traceparent else None
        return ports.RecordedResponse(
            status=response.get("status", 200),
            headers={},
            json=copy.deepcopy(response.get("json")),
            text="",
            trace_id=trace_id,
            request=spec,
        )


def _resolver(scenario, step, template):
    return ports.RequestSpec(
        method=template.method,
        path=template.path,
        body=template.body or {},
    )


def _flow(
    *,
    target_path="targets/{value}",
    target_expect=None,
    bindings=None,
    poll=None,
):
    return Scenario(
        id="binding_diagnostics",
        grid=Grid("regression", "generic"),
        actor="actor",
        precondition=[],
        inputs=[],
        intent="diagnose cross-step identity",
        steps=[
            Step(
                id="source",
                request=RequestTemplate("POST", "source"),
                expect=Expect(response=[Assertion("success", {})]),
            ),
            Step(
                id="target",
                request=RequestTemplate("GET", target_path),
                expect=target_expect or Expect(
                    response=[Assertion("success", {})]
                ),
                bind=bindings or [Binding("value", "source", "value")],
                poll=poll,
            ),
        ],
    )


def _run(scenario, api, *, normalizer=None, state=None, **kwargs):
    return backend.run(
        scenario,
        auth=FakeAuth(),
        api=api,
        state=state,
        recorder=FakeRecorder(),
        resolve_request=_resolver,
        normalizer=normalizer or FakeNormalizer(),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("target_success", "expected_status"),
    [(True, PASSED), (False, FAILED)],
)
def test_regular_step_keeps_resolved_bindings_when_passed_or_failed(
    target_success, expected_status
):
    api = FakeApi(responses={
        ("POST", "source"): {
            "status": 200,
            "json": {"success": True, "data": {"value": 7}},
        },
        ("GET", "targets/7"): {
            "status": 200,
            "json": {"success": target_success, "data": {}},
        },
    })

    result = _run(_flow(), api)

    assert result.steps[0].resolved_bindings == {}
    assert result.steps[1].status == expected_status
    assert result.steps[1].resolved_bindings == {"value": 7}


@pytest.mark.parametrize(
    ("outcome", "on_timeout", "expected_status"),
    [
        ("ready", "FAIL", PASSED),
        ("timeout", "FAIL", FAILED),
        ("timeout", "SKIP", SKIPPED),
    ],
)
def test_poll_step_keeps_resolved_bindings_for_every_terminal_status(
    outcome, on_timeout, expected_status
):
    pending = {"status": 200, "json": {"success": True, "data": {}}}
    target_responses = [pending]
    if outcome == "ready":
        target_responses.append({
            "status": 200,
            "json": {"success": True, "data": {"result": "done"}},
        })
    api = SequencedApi({
        ("POST", "source"): [{
            "status": 200,
            "json": {"success": True, "data": {"job_id": 9}},
        }],
        ("GET", "jobs/9"): target_responses,
    })
    scenario = _flow(
        target_path="jobs/{job_id}",
        target_expect=Expect(response=[Assertion("has", {"field": "result"})]),
        bindings=[Binding("job_id", "source", "job_id")],
        poll=PollPolicy(on_timeout),
    )
    clock = FakeClock()

    result = _run(
        scenario,
        api,
        poll_config=types.SimpleNamespace(timeout=2, interval=1),
        now=clock.now,
        sleep=clock.sleep,
    )

    assert result.steps[1].status == expected_status
    assert result.steps[1].resolved_bindings == {"job_id": 9}


@pytest.mark.parametrize("error_stage", ["send", "normalizer", "state_probe"])
def test_error_after_binding_keeps_resolved_bindings(error_stage):
    target_expect = Expect(response=[Assertion("success", {})])
    if error_stage == "state_probe":
        target_expect.backend_state = [
            Assertion("span_exists", {"span": "target.read"})
        ]
    scenario = _flow(target_expect=target_expect)

    class ErrorApi(FakeApi):
        def send(self, spec, session):
            if error_stage == "send" and spec.path == "targets/7":
                raise RuntimeError("send failed after binding")
            return super().send(spec, session)

    class ErrorNormalizer(FakeNormalizer):
        def normalize(self, response):
            if error_stage == "normalizer" and response.request.path == "targets/7":
                raise RuntimeError("normalization failed after binding")
            return super().normalize(response)

    class ErrorState:
        def observe(self, trace_id):
            raise RuntimeError("state observation failed after binding")

    api = ErrorApi(responses={
        ("POST", "source"): {
            "status": 200,
            "json": {"success": True, "data": {"value": 7}},
        },
        ("GET", "targets/7"): {
            "status": 200,
            "json": {"success": True, "data": {}},
        },
    })

    result = _run(
        scenario,
        api,
        normalizer=ErrorNormalizer(),
        state=ErrorState() if error_stage == "state_probe" else None,
    )

    assert result.steps[1].status == ERROR
    assert result.steps[1].resolved_bindings == {"value": 7}


def test_partial_binding_resolution_error_discards_all_values():
    scenario = _flow(
        target_path="targets",
        bindings=[
            Binding("first", "source", "present"),
            Binding("second", "source", "missing"),
        ],
    )
    api = FakeApi(responses={
        ("POST", "source"): {
            "status": 200,
            "json": {"success": True, "data": {"present": "kept-only-internally"}},
        },
    })

    result = _run(scenario, api)

    assert result.steps[1].status == ERROR
    assert result.steps[1].resolved_bindings == {}
    assert len(api.sent) == 1


def test_blocked_step_with_declared_binding_has_no_resolved_values():
    scenario = _flow()
    scenario.steps[0].expect = Expect(
        response=[Assertion("has", {"field": "required_but_missing"})]
    )
    api = FakeApi(responses={
        ("POST", "source"): {
            "status": 200,
            "json": {"success": True, "data": {"value": 7}},
        },
    })

    result = _run(scenario, api)

    assert result.steps[0].status == FAILED
    assert result.steps[1].status == BLOCKED
    assert result.steps[1].resolved_bindings == {}
    assert len(api.sent) == 1


def test_resolved_bindings_preserve_falsy_values():
    scenario = _flow(
        target_path="consume",
        bindings=[
            Binding("zero", "source", "zero"),
            Binding("empty", "source", "empty"),
            Binding("flag", "source", "flag"),
        ],
    )
    api = FakeApi(responses={
        ("POST", "source"): {
            "status": 200,
            "json": {
                "success": True,
                "data": {"zero": 0, "empty": "", "flag": False},
            },
        },
        ("GET", "consume"): {
            "status": 200,
            "json": {"success": True, "data": {}},
        },
    })

    result = _run(scenario, api)

    assert result.steps[1].status == PASSED
    assert result.steps[1].resolved_bindings == {
        "zero": 0,
        "empty": "",
        "flag": False,
    }


def test_diagnostic_mapping_is_a_distinct_shallow_copy_of_execution_values(
    monkeypatch,
):
    nested = {"items": [1]}
    execution_mapping = {"value": nested}
    seen = {}
    original_run_step = backend._run_step

    def fake_resolve_bindings(step, prior_norms):
        if step.id == "target":
            return execution_mapping
        return {}

    def capture_run_step(*args, **kwargs):
        if args[0].id == "target":
            seen["bound_values"] = args[-2]
        return original_run_step(*args, **kwargs)

    monkeypatch.setattr(backend.binding, "resolve_bindings", fake_resolve_bindings)
    monkeypatch.setattr(backend, "_run_step", capture_run_step)
    api = FakeApi(responses={
        ("POST", "source"): {
            "status": 200,
            "json": {"success": True, "data": {}},
        },
        ("GET", "targets/{value}"): {
            "status": 200,
            "json": {"success": True, "data": {}},
        },
    })

    result = _run(_flow(), api)
    diagnostic_mapping = result.steps[1].resolved_bindings

    assert seen["bound_values"] is execution_mapping
    assert diagnostic_mapping == execution_mapping
    assert diagnostic_mapping is not seen["bound_values"]
    assert diagnostic_mapping["value"] is nested
