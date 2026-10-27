"""Live primitive loop: independently owned state, recordings and real evidence."""
import copy
import dataclasses
import pytest
from refracto import ports
from refracto.declaration.model import Assertion, Binding, Expect, PollPolicy, RequestTemplate, Step
from refracto.projection import e2e
from refracto.runner import PollConfig
from refracto.report import RunReport
from tests.fakes import FakeApi, FakeAuth, FakeNormalizer, FakeRecorder
from tests.ui_support import ScriptedUi, response, run, scenario


class LiveState(ports.StateProbe):
    def __init__(self, mode="ok"):
        self.mode, self.calls = mode, []

    def observe(self, trace):
        self.calls.append(trace)
        if self.mode == "raise":
            raise RuntimeError("state error")
        if self.mode == "wrong-type":
            return {"trace_id": trace}
        return ports.StateFacts("wrong" if self.mode == "wrong-trace" else trace,
                                [] if self.mode == "empty" else [ports.Span("created")])


class Clock:
    def __init__(self): self.value = 0
    def now(self): return self.value
    def sleep(self, duration): self.value += duration


def test_missing_or_failing_auth_stops_before_context_and_recordings():
    class BrokenAuth(FakeAuth):
        def session(self, role): raise RuntimeError("auth error")
    for auth in (None, BrokenAuth()):
        ui, recorder = ScriptedUi(), FakeRecorder()
        result = run(scenario(), ui, auth=auth, recorder=recorder)
        assert [r.status for r in result.steps] == ["ERROR", "BLOCKED"]
        assert ui.open_calls == 0 and not recorder.responses()


@pytest.mark.parametrize("supported", [False, 1, "true"])
def test_capability_requires_true_before_auth_or_context(supported):
    class Driver(ScriptedUi):
        def supports_stepwise_mode(self, mode): return supported
    ui = Driver()
    assert run(scenario(), ui).steps[0].status == "ERROR"
    assert ui.open_calls == 0


def test_live_has_one_context_and_four_points_using_selected_trace():
    ui, state = ScriptedUi(), LiveState()
    result = run(scenario(state=True, references=True), ui, state=state)
    assert result.status == "PASSED"
    assert len(result.provider_recordings) == 2
    assert [r.step_id for r in result.provider_recordings] == ["s0", "s1"]
    assert state.calls == [r.trace_id for r in result.provider_recordings]
    assert len(set(state.calls)) == 2
    assert all({c.point for c in s.checks} == {"frontend", "request", "response", "backend_state"}
               for s in result.steps)
    assert ui.open_calls == ui.close_calls == 1
    assert result.steps[1].resolved_bindings == {"previous": "1"}


def test_normalizer_cannot_rewrite_protected_recording_identity():
    class Mutating(FakeNormalizer):
        def normalize(self, raw):
            norm = super().normalize(raw)
            raw.step_id = "rewritten"
            raw.trace_id = "forged"
            raw.request.path = "wrong"
            return norm
    result = run(scenario(), ScriptedUi(), normalizer=Mutating())
    assert result.status == "PASSED"
    assert [r.step_id for r in result.provider_recordings] == ["s0", "s1"]
    assert all(r.request.path == "items" and r.trace_id != "forged" for r in result.provider_recordings)


@pytest.mark.parametrize("stage", ["adapter", "normalizer", "record", "responses", "state"])
def test_each_error_preserves_binding_and_blocks(stage):
    class Normalizer(FakeNormalizer):
        def normalize(self, raw):
            if stage == "normalizer" and raw.step_id == "s1": raise RuntimeError("normalizer error")
            return super().normalize(raw)
    class Recorder(FakeRecorder):
        def record(self, raw):
            if stage == "record" and raw.step_id == "s1": raise RuntimeError("record error")
            super().record(raw)
        def responses(self):
            if stage == "responses" and len(self._responses) == 2: raise RuntimeError("responses error")
            return super().responses()
    class State(LiveState):
        def observe(self, trace):
            if stage == "state" and self.calls: raise RuntimeError("state error")
            return super().observe(trace)
    ui = ScriptedUi(3, terminal=(1, "error") if stage == "adapter" else None)
    result = run(scenario(count=3, references=True, state=True), ui,
                 normalizer=Normalizer(), recorder=Recorder(), state=State())
    assert [r.status for r in result.steps] == ["PASSED", "ERROR", "BLOCKED"]
    assert result.steps[1].resolved_bindings == {"previous": "1"}
    assert ui.close_calls == 1


@pytest.mark.parametrize("tamper", ["extra", "missing", "reverse", "identity", "type"])
def test_recorder_count_order_and_identity_are_validated(tamper):
    class Recorder(FakeRecorder):
        def responses(self):
            result = copy.deepcopy(super().responses())
            if len(result) == 2:
                if tamper == "extra": result += [result[0]]
                elif tamper == "missing": result.pop()
                elif tamper == "reverse": result.reverse()
                elif tamper == "identity": result[-1].step_id = "wrong"
                else: result[-1].attempt_index = False
            return result
    result = run(scenario(), ScriptedUi(), recorder=Recorder())
    assert result.steps[1].status == "ERROR"


def test_background_same_path_cannot_replace_primary_or_enter_recorder():
    def diagnostic(index, result, permit):
        e = result.evidence
        raw = copy.deepcopy(e.traffic[0].response)
        raw.trace_id, raw.request.traceparent, raw.step_id = "background", "00-background-parent-01", None
        raw.request_id = f"background-{index}"
        return ports.UiActionResult(evidence=dataclasses.replace(
            e, diagnostic_outgoing=[raw.request], diagnostic_recorded=[raw]))
    result = run(scenario(), ScriptedUi(mutate=diagnostic))
    assert result.status == "PASSED"
    assert len(result.provider_recordings) == 2
    def only_background(index, result, permit):
        wrapped = diagnostic(index, result, permit)
        return ports.UiActionResult(evidence=dataclasses.replace(wrapped.evidence, traffic=[]))
    result = run(scenario(), ScriptedUi(mutate=only_background))
    assert [r.status for r in result.steps] == ["ERROR", "BLOCKED"]
    assert result.provider_recordings == []


@pytest.mark.parametrize("source", ["current", "previous"])
@pytest.mark.parametrize("stream", ["outgoing", "recorded-request", "recorded-trace", "recorded-id"])
def test_diagnostics_cannot_relabel_current_or_prior_accepted_identity(source, stream):
    prior = []
    def tamper(index, result, permit):
        e = result.evidence
        accepted = copy.deepcopy(e.traffic[0].response)
        if source == "previous" and not index:
            prior.append(accepted)
            return result
        if source == "previous":
            accepted = prior[0]
        if stream == "outgoing":
            # The actual RequestSpec is copied, not the same Python object.
            changed = dataclasses.replace(e, diagnostic_outgoing=[copy.deepcopy(accepted.request)])
        else:
            diagnostic = copy.deepcopy(accepted)
            diagnostic.request_id = "unaccepted-request"
            diagnostic.trace_id = "unaccepted-trace"
            diagnostic.request.traceparent = "00-unaccepted-traceparent-01"
            if stream == "recorded-request":
                # Foreign outer IDs must not hide the accepted nested request.
                diagnostic.request = copy.deepcopy(accepted.request)
            elif stream == "recorded-trace":
                diagnostic.trace_id = accepted.trace_id
            else:
                diagnostic.request_id = accepted.request_id
            changed = dataclasses.replace(e, diagnostic_recorded=[diagnostic])
        return ports.UiActionResult(evidence=changed)
    ui = ScriptedUi(3, mutate=tamper)
    result = run(scenario(count=3), ui)
    expected = ["ERROR", "BLOCKED", "BLOCKED"] if source == "current" else ["PASSED", "ERROR", "BLOCKED"]
    assert [s.status for s in result.steps] == expected
    assert len(result.provider_recordings) == (source == "previous")
    assert len(ui.permits) == (1 if source == "current" else 2)
    assert ui.close_calls == 1


@pytest.mark.parametrize("field", ["outgoing-traceparent", "recorded-traceparent", "trace_id", "request_id"])
@pytest.mark.parametrize("value", [False, 0, True, 1, [], {}, ""])
def test_diagnostic_correlation_identity_types_are_strict(field, value):
    def tamper(index, result, permit):
        e = result.evidence
        diagnostic = copy.deepcopy(e.traffic[0].response)
        diagnostic.trace_id = diagnostic.request_id = None
        diagnostic.request.traceparent = None
        if field.endswith("traceparent"):
            diagnostic.request.traceparent = value
        else:
            setattr(diagnostic, field, value)
        changed = (dataclasses.replace(e, diagnostic_outgoing=[diagnostic.request])
                   if field == "outgoing-traceparent" else
                   dataclasses.replace(e, diagnostic_recorded=[diagnostic]))
        return ports.UiActionResult(evidence=changed)
    result = run(scenario(), ScriptedUi(mutate=tamper))
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert result.provider_recordings == []


@pytest.mark.parametrize("correlation", ["absent", "unaccepted-late"])
def test_unaccepted_background_diagnostics_remain_valid_but_not_target_evidence(correlation):
    def diagnostic(index, result, permit):
        raw = copy.deepcopy(result.evidence.traffic[0].response)
        raw.request_id = None if correlation == "absent" else "unobserved-request"
        raw.trace_id = None if correlation == "absent" else "unobserved"
        raw.request.traceparent = None if correlation == "absent" else "00-unobserved-parent-01"
        raw.step_id = "earlier-action-never-accepted"
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence, diagnostic_outgoing=[raw.request], diagnostic_recorded=[raw]))
    result = run(scenario(), ScriptedUi(mutate=diagnostic))
    assert result.status == "PASSED"
    assert [r.step_id for r in result.provider_recordings] == ["s0", "s1"]
    assert all(r.request_id != "unobserved-request" for r in result.provider_recordings)
    def only_diagnostic(index, result, permit):
        evidence = diagnostic(index, result, permit).evidence
        return ports.UiActionResult(evidence=dataclasses.replace(evidence, traffic=[]))
    result = run(scenario(), ScriptedUi(mutate=only_diagnostic))
    assert [s.status for s in result.steps] == ["ERROR", "BLOCKED"]
    assert result.provider_recordings == []


def test_delayed_prior_response_does_not_become_current_evidence():
    prior = []
    def delay(index, result, permit):
        if not index:
            prior.append(copy.deepcopy(result.evidence.traffic[0].response))
            return result
        return ports.UiActionResult(evidence=dataclasses.replace(
            result.evidence, traffic=[], diagnostic_recorded=prior))
    result = run(scenario(), ScriptedUi(mutate=delay))
    assert result.steps[1].status == "ERROR"
    assert len(result.provider_recordings) == 1


@pytest.mark.parametrize("target", ["request", "response"])
def test_mismatched_trace_request_pairs_fail(target):
    def tamper(i, result, permit):
        traffic = result.evidence.traffic[0]
        if target == "request":
            traffic.request.traceparent = "00-wrong-parent-01"
        else:
            traffic.response.request.body = {"name": False}
        return result
    assert run(scenario(), ScriptedUi(mutate=tamper)).steps[0].status == "ERROR"


@pytest.mark.parametrize("mode", ["wrong-type", "wrong-trace", "raise"])
def test_state_facts_type_trace_and_exception_are_not_success(mode):
    result = run(scenario(state=True), ScriptedUi(), state=LiveState(mode))
    assert [r.status for r in result.steps] == ["ERROR", "BLOCKED"]


def test_state_only_when_declared_missing_state_visible_and_poll_is_not_ui_replay():
    state = LiveState()
    assert run(scenario(), ScriptedUi(), state=state).status == "PASSED"
    assert state.calls == []
    result = run(scenario(state=True), ScriptedUi())
    assert result.status == "DEGRADED" and all(s.skipped for s in result.steps)
    class Eventually(LiveState):
        def observe(self, trace):
            self.calls.append(trace)
            return ports.StateFacts(trace, [ports.Span("created")] if len(self.calls) > 1 else [])
    clock, ui, state = Clock(), ScriptedUi(1), Eventually()
    result = run(scenario(count=1, state=True), ui, state=state,
                 poll_config=PollConfig(timeout=2, interval=1), now=clock.now, sleep=clock.sleep)
    assert result.status == "PASSED"
    assert len(state.calls) == 2 and len(ui.permits) == 1


def test_every_state_poll_revalidates_identity_and_empty_final_state_fails():
    class WrongLater(LiveState):
        def observe(self, trace):
            self.calls.append(trace)
            return ports.StateFacts(trace if len(self.calls) == 1 else "stale", [])
    clock = Clock()
    result = run(scenario(state=True), ScriptedUi(), state=WrongLater(),
                 poll_config=PollConfig(timeout=1, interval=1), now=clock.now, sleep=clock.sleep)
    assert result.steps[0].status == "ERROR"
    clock = Clock()
    result = run(scenario(state=True), ScriptedUi(), state=LiveState("empty"),
                 poll_config=PollConfig(timeout=1, interval=1), now=clock.now, sleep=clock.sleep)
    assert [r.status for r in result.steps] == ["FAILED", "FAILED"]


@pytest.mark.parametrize("kind", ["frontend", "request", "response"])
def test_assertion_failure_is_failed_not_protocol_error(kind):
    s, ui = scenario(), ScriptedUi()
    if kind == "frontend": ui.renders[0] = {}
    elif kind == "request": ui.requests[0][0].body = {"name": "wrong"}
    else: ui.payloads[0] = {"success": False}
    result = run(s, ui)
    assert [r.status for r in result.steps] == ["FAILED", "PASSED"]


def test_explicit_api_e2e_needs_no_ui_and_poll_uses_actual_attempts():
    s = scenario(count=1)
    s.steps[0] = Step("read", RequestTemplate("GET", "status"),
                      Expect(response=[Assertion("has", {"field": "ready"})]),
                      poll=PollPolicy("FAIL"), action="request")
    class Api(FakeApi):
        def send(self, spec, session):
            self.responses = {("GET", "status"): {"json": response({"ready": True} if self.sent else {})}}
            return super().send(spec, session)
    api, clock, ui = Api(), Clock(), ScriptedUi()
    result = run(s, ui, api=api,
                 resolve_request=lambda t: ports.RequestSpec(t.method, t.path, t.body),
                 poll_config=PollConfig(timeout=2, interval=1), now=clock.now, sleep=clock.sleep)
    assert result.status == "PASSED"
    assert len(api.sent) == 2 and ui.open_calls == 0
    assert [r.is_final for r in result.provider_recordings] == [False, True]


def _mixed_api_ui_case(polling, mutate=None):
    s = scenario(count=3)
    s.steps[0] = Step("api", RequestTemplate("GET", "status"),
                      Expect(response=[Assertion("has", {"field": "ready"})]),
                      poll=PollPolicy("FAIL") if polling else None, action="request")
    class Api(FakeApi):
        def send(self, spec, session):
            data = {"ready": True} if not polling or self.sent else {}
            self.responses = {("GET", "status"): {"json": response(data)}}
            return super().send(spec, session)
    recorder, api, clock = FakeRecorder(), Api(), Clock()
    def edit(index, result, permit):
        return mutate(index, result, recorder) if mutate else result
    ui = ScriptedUi(mutate=edit)
    result = run(s, ui, api=api, recorder=recorder,
                 resolve_request=lambda t: ports.RequestSpec(t.method, t.path, t.body),
                 poll_config=PollConfig(timeout=2, interval=1), now=clock.now, sleep=clock.sleep)
    return result, ui, api


@pytest.mark.parametrize("polling", [False, True])
def test_mixed_api_then_ui_keeps_independent_actual_correlations(polling):
    result, ui, api = _mixed_api_ui_case(polling)
    assert result.status == "PASSED"
    assert [s.status for s in result.steps] == ["PASSED"] * 3
    assert len(api.sent) == (2 if polling else 1)
    assert len(ui.permits) == 2
    records = result.provider_recordings
    assert [r.step_id for r in records] == (["api"] * len(api.sent) + ["s1", "s2"])
    assert len({r.request_id for r in records}) == len(records)
    assert len({r.trace_id for r in records}) == len(records)
    assert ui.open_calls == ui.close_calls == 1


@pytest.mark.parametrize("source", ["single", "poll-first", "poll-final"])
@pytest.mark.parametrize("stream", ["outgoing", "recorded-request", "recorded-trace",
                                     "recorded-id", "primary-trace", "primary-id"])
def test_ui_cannot_reuse_accepted_api_or_polling_identity(source, stream):
    def tamper(index, result, recorder):
        accepted = copy.deepcopy(recorder.responses()[-1 if source == "poll-final" else 0])
        assert accepted.is_final is (source != "poll-first")
        assert type(accepted.request_id) is str and type(accepted.trace_id) is str
        e, traffic = result.evidence, result.evidence.traffic[0]
        if stream == "outgoing":
            changed = dataclasses.replace(e, diagnostic_outgoing=[accepted.request])
        elif stream.startswith("primary"):
            raw = copy.deepcopy(traffic.response)
            request = copy.deepcopy(traffic.request)
            request_id = traffic.request_id
            if stream == "primary-trace":
                request.traceparent = accepted.request.traceparent
                raw.trace_id = accepted.trace_id
            else:
                request_id = accepted.request_id
            raw.request, raw.request_id = copy.deepcopy(request), request_id
            changed = dataclasses.replace(e, traffic=[dataclasses.replace(
                traffic, request=request, response=raw, request_id=request_id)])
        else:
            raw = copy.deepcopy(accepted)
            raw.request_id, raw.trace_id, raw.request.traceparent = None, None, None
            if stream == "recorded-request":
                raw.request = copy.deepcopy(accepted.request)
            elif stream == "recorded-trace":
                raw.trace_id = accepted.trace_id
            else:
                raw.request_id = accepted.request_id
            changed = dataclasses.replace(e, diagnostic_recorded=[raw])
        return ports.UiActionResult(evidence=changed)
    result, ui, api = _mixed_api_ui_case(source != "single", tamper)
    assert [s.status for s in result.steps] == ["PASSED", "ERROR", "BLOCKED"]
    assert len(result.provider_recordings) == len(api.sent)
    assert all(r.step_id == "api" for r in result.provider_recordings)
    assert len(ui.permits) == 1 and ui.close_calls == 1


def test_ui_failure_never_calls_api_to_repair_missing_request():
    api = FakeApi()
    result = run(scenario(), ScriptedUi(requests=[[], []]), api=api,
                 resolve_request=lambda t: ports.RequestSpec(t.method, t.path, t.body))
    assert result.steps[0].status == "ERROR"
    assert api.sent == []


def test_report_repr_hides_sensitive_live_payload_and_error_detail():
    secret = "live-sensitive-sentinel"
    ui = ScriptedUi(payloads=[response({"id": secret}), response()])
    domain = run(scenario(references=True), ui)
    assert domain.status == "PASSED"
    assert secret not in repr(domain)
    assert secret not in repr(RunReport("test", [domain]))
    assert secret not in repr(ui.evidence)


@pytest.mark.parametrize("terminal, expected", [("failed", "FAILED"), ("error", "ERROR"), ("skip", "SKIPPED")])
def test_live_c5_all_post_resolution_terminal_states_keep_bindings(terminal, expected):
    ui = ScriptedUi(3, terminal=(1, terminal))
    if terminal == "failed": ui.renders[1] = {}
    result = run(scenario(count=3, references=True), ui)
    assert [r.status for r in result.steps] == ["PASSED", expected, "PASSED" if terminal == "failed" else "BLOCKED"]
    assert result.steps[1].resolved_bindings == {"previous": "1"}
    assert not hasattr(ui.permits[1], "resolved_bindings")
    assert result.steps[2].resolved_bindings == ({"previous": "1"} if terminal == "failed" else {})
    assert ui.close_calls == 1


def test_live_c5_atomic_failure_blocked_and_falsy_values():
    s = scenario(count=3, references=True)
    s.steps[1].bind.append(Binding("other", "s0", "missing"))
    ui = ScriptedUi(3)
    result = run(s, ui)
    assert [r.status for r in result.steps] == ["PASSED", "BLOCKED", "PASSED"]
    assert result.steps[1].resolved_bindings == {}
    assert result.steps[2].resolved_bindings == {"previous": "1"}
    assert len(ui.permits) == 2
    for value in (False, 0, ""):
        result = run(scenario(references=True), ScriptedUi(payloads=[response({"id": value}), response()]))
        assert result.status == "PASSED"
        assert type(result.steps[1].resolved_bindings["previous"]) is type(value)


def test_unavailable_or_throwing_context_never_performs_action():
    class Driver(ScriptedUi):
        def open_stepwise(self, session, *, mode, mock_plan=None, **identity):
            self.open_calls += 1
            raise RuntimeError("cannot open")
    ui = Driver()
    result = run(scenario(), ui)
    assert [r.status for r in result.steps] == ["ERROR", "BLOCKED"]
    assert ui.open_calls == 1 and ui.close_calls == 0 and ui.permits == []


def test_frontend_and_e2e_separate_contexts_not_shared_physical_execution():
    ui = ScriptedUi(1)
    assert run(scenario(count=1), ui, mode="mock").status == "PASSED"
    ui.permits.clear()
    assert run(scenario(count=1), ui).status == "PASSED"
    assert ui.open_calls == ui.close_calls == 2
    assert ui.contexts[0] is not ui.contexts[2]


def test_live_same_run_and_cross_run_action_replay_and_swapped_requests_are_rejected():
    cached = []
    def replay(i, result, permit):
        if not cached: cached.append(result)
        return cached[0]
    first = run(scenario(), ScriptedUi(mutate=replay))
    second = run(scenario(), ScriptedUi(mutate=replay))
    assert first.steps[1].status == second.steps[0].status == "ERROR"
    def swap(i, result, permit):
        traffic = result.evidence.traffic
        traffic[0].response.request_id, traffic[1].response.request_id = traffic[1].request_id, traffic[0].request_id
        return result
    requests = [[ports.RequestSpec("POST", "items", {"name": "alpha"}), ports.RequestSpec("GET", "status")]]
    assert run(scenario(count=1), ScriptedUi(1, requests=requests, mutate=swap)).steps[0].status == "ERROR"


@pytest.mark.parametrize("component", ["state", "record", "responses", "request-pair", "trace"])
def test_direct_api_e2e_has_the_same_strict_port_boundaries(component):
    s = scenario(count=1)
    s.steps[0] = Step("read", RequestTemplate("GET", "status"),
                      Expect(response=[Assertion("success")], backend_state=[Assertion("span_exists", {"span": "created"})]),
                      action="request")
    class Api(FakeApi):
        def send(self, spec, session):
            raw = super().send(spec, session)
            if component == "request-pair": raw.request.path = "wrong"
            if component == "trace": raw.trace_id = "wrong"
            return raw
    class Recorder(FakeRecorder):
        def record(self, raw):
            if component == "record": raise RuntimeError("record")
            super().record(raw)
        def responses(self):
            if component == "responses": raise RuntimeError("responses")
            return super().responses()
    result = run(s, None, api=Api(), state=LiveState("wrong-trace" if component == "state" else "ok"),
                 recorder=Recorder(), resolve_request=lambda t: ports.RequestSpec(t.method, t.path, t.body))
    assert result.steps[0].status == "ERROR"


def test_paired_direct_api_without_server_trace_uses_local_correlation_not_state_proof():
    class NoServerTrace(FakeApi):
        def send(self, spec, session):
            return dataclasses.replace(super().send(spec, session), trace_id=None)
    s = scenario(count=1)
    s.steps[0] = Step("read", RequestTemplate("GET", "status"),
                      Expect(response=[Assertion("success")]), action="request")
    mapping = lambda t: ports.RequestSpec(t.method, t.path, t.body)
    api = NoServerTrace()
    result = run(s, None, api=api, resolve_request=mapping)
    assert result.status == "PASSED"
    assert result.provider_recordings[0].trace_id == api.sent[0].traceparent.split("-")[1]
    s.steps[0].expect.backend_state = [Assertion("span_exists", {"span": "created"})]
    assert run(s, None, api=NoServerTrace(), resolve_request=mapping).status == "DEGRADED"
    clock = Clock()
    result = run(s, None, api=NoServerTrace(), resolve_request=mapping, state=LiveState("empty"),
                 now=clock.now, sleep=clock.sleep)
    assert result.status == "FAILED"
