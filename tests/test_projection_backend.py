import copy
import types

import pytest

from refracto.projection import backend
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Scenario, Grid, Expect, Assertion, Step
from refracto.runner import PollConfig
from refracto import ports
from refracto.report import DomainResult, PASSED, FAILED, SKIPPED, ERROR, BLOCKED, DEGRADED
from tests.fakes import FakeAuth, FakeApi, FakeStateProbe, FakeRecorder, FakeNormalizer

def _resolver(scenario, step, template):
    return ports.RequestSpec(method=template.method, path=template.path,
                             body=template.body or {})

class FakeClock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, s): self.t += s

def test_gen_traceparent_shape():
    tp = backend.gen_traceparent()
    parts = tp.split("-")
    assert parts[0] == "00" and len(parts[1]) == 32 and len(parts[2]) == 16 and parts[3] == "01"

def test_backend_all_green():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    api = FakeApi(responses={("POST", "resource/action"):
        {"status": 200, "json": {"success": True, "data": {"taskId": "T1"}}}})
    # the trace id is generated inside backend.run; FakeStateProbe must answer for ANY trace id:
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [
        ports.Span("POST /resource/action"),
        ports.Span("INSERT resource.job_queue")])
    res = backend.run(s, auth=FakeAuth(), api=api, state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert res.passed
    assert any(c.check == "success" and c.ok for c in res.checks)
    assert any(c.check == "has" and c.ok for c in res.checks)
    assert sum(1 for c in res.checks if c.check == "span_exists" and c.ok) == 2

def test_backend_response_fail_when_missing_field():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    api = FakeApi(responses={("POST", "resource/action"):
        {"status": 200, "json": {"success": True, "data": {}}}})   # no taskId
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [
        ports.Span("POST /resource/action"),
        ports.Span("INSERT resource.job_queue")])
    res = backend.run(s, auth=FakeAuth(), api=api, state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert not res.passed
    assert any(c.check == "has" and not c.ok for c in res.checks)

def test_backend_state_skipped_when_no_probe():
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    api = FakeApi(responses={("POST", "resource/action"):
        {"status": 200, "json": {"success": True, "data": {"taskId": "T1"}}}})
    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    # response checks still pass; backend_state degraded to skipped
    assert any(c.check == "success" and c.ok for c in res.checks)
    assert any("span_exists" in sk for step in res.steps for sk in step.skipped)
    assert res.passed   # skipped does not fail the domain

def test_response_expectations_without_request_assertions():
    """Regression test (migrated to the step model): a step with no request template
    but declared response expectations must not crash with an AttributeError on a
    None template — instead the step becomes ERROR via the run()'s try/except, and
    the domain does not crash."""
    s = Scenario(
        id="test_no_request",
        grid=Grid("integration", "dataset"),
        actor="admin",
        precondition=[],
        inputs=[],
        intent="test response expectations without request",
        steps=[Step(id="main", request=None,
                    expect=Expect(response=[Assertion("success", {})]))],
    )

    def never_called_resolver(scenario, step, template):
        raise AssertionError("resolve_request should not be called")

    res = backend.run(s, auth=FakeAuth(), api=FakeApi(responses={}),
                      state=None, recorder=FakeRecorder(),
                      resolve_request=never_called_resolver, normalizer=FakeNormalizer())

    assert res is not None
    assert isinstance(res, DomainResult)
    assert res.passed is False
    assert len(res.steps) == 1
    assert res.steps[0].status == ERROR

def test_backend_state_timeout_reports_failing_check_not_crash():
    """Regression test: when the wanted backend_state span never appears, wait_until
    (on_timeout=FAIL) raises TimeoutError internally. backend.run must catch it and
    report a failing CheckResult instead of letting the exception escape."""
    s = load_scenario("tests/fixtures/synthetic_scenario.yaml")
    api = FakeApi(responses={("POST", "resource/action"):
        {"status": 200, "json": {"success": True, "data": {"taskId": "T1"}}}})
    clock = FakeClock()
    state = FakeStateProbe()
    # Always observe spans that do NOT include the wanted spans.
    state.observe = lambda tid: ports.StateFacts(tid, [ports.Span("some.other.span", {})])

    poll_config = types.SimpleNamespace(timeout=3, interval=1)
    res = backend.run(s, auth=FakeAuth(), api=api, state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)

    assert isinstance(res, DomainResult)
    assert res.passed is False

    # On timeout, backend-state evaluation reports the specific failing assertions rather than a generic
    # span_timeout summary) — both wanted spans are missing.
    failing = [c for c in res.checks if c.check == "span_exists" and not c.ok]
    assert len(failing) == 2
    details = " ".join(c.detail for c in failing)
    assert "POST /resource/action" in details
    assert "INSERT resource.job_queue" in details

def test_backend_span_attr_still_supported(tmp_path):
    """span_attr stays a core capability (used once the product emits semantic spans);
    the shipped scenario no longer uses it, so cover it via a synthetic scenario."""
    y = tmp_path / "s.yaml"
    y.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: []\nintent: t\n"
        "expect:\n"
        "  request:\n    - {check: request, method: POST, path: p}\n"
        "  backend_state:\n"
        "    - {check: span_attr, span: dataset.import, attr: row_count, op: '>', value: 0}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    api = FakeApi()
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [ports.Span("dataset.import", {"row_count": 3})])
    res = backend.run(s, auth=FakeAuth(), api=api, state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert any(c.check == "span_attr" and c.ok for c in res.checks)


_SPAN_ATTR_YAML = (
    "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
    "precondition: []\ninputs: []\nintent: t\n"
    "expect:\n  request:\n    - {check: request, method: POST, path: p}\n"
    "  backend_state:\n"
    "    - {check: span_attr, span: dataset.import, attr: row_count, op: '>', value: 0}\n"
)


def test_span_attr_any_matching_span_passes(tmp_path):
    """Duplicate span names do not overwrite one another. Any matching span whose attribute satisfies the comparison is sufficient."""
    y = tmp_path / "s.yaml"
    y.write_text(_SPAN_ATTR_YAML, encoding="utf-8")
    s = load_scenario(str(y))
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [
        ports.Span("dataset.import", {"row_count": 5}),   # satisfies row_count > 0
        ports.Span("dataset.import", {"row_count": 0})])  # last; old last-wins would pick this
    res = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert any(c.check == "span_attr" and c.ok for c in res.checks)


def test_span_exists_with_duplicate_names(tmp_path):
    """Repeated span names still satisfy `span_exists` deterministically."""
    y = tmp_path / "s.yaml"
    y.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: []\nintent: t\n"
        "expect:\n  request:\n    - {check: request, method: POST, path: p}\n"
        "  backend_state:\n    - {check: span_exists, span: item.create}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [
        ports.Span("item.create", {"row_count": 1}),
        ports.Span("item.create", {"row_count": 2})])
    res = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert any(c.check == "span_exists" and c.ok for c in res.checks)


def test_backend_state_polls_until_attr_materializes(tmp_path):
    """Backend-state polling waits for the full assertion predicate, not merely for a span name to appear."""
    y = tmp_path / "s.yaml"
    y.write_text(_SPAN_ATTR_YAML, encoding="utf-8")
    s = load_scenario(str(y))
    clock = FakeClock()
    state = FakeStateProbe()
    calls = {"n": 0}

    def observe(tid):
        calls["n"] += 1
        rc = 5 if calls["n"] >= 3 else 0
        return ports.StateFacts(tid, [ports.Span("dataset.import", {"row_count": rc})])

    state.observe = observe
    poll_config = types.SimpleNamespace(timeout=30, interval=1)
    res = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)
    assert any(c.check == "span_attr" and c.ok for c in res.checks)
    assert calls["n"] >= 3   # kept polling past the span appearing until the attr held


# --- S1: ordered binding ------------------------------------------------------

def test_backend_runs_ordered_steps_with_binding(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(
        "version: 2\n"
        "scenario: flow\ngrid: {level: r, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: success}\n"
        "        - {check: has, field: jobId}\n"
        "  - id: fetch\n"
        "    request: {method: GET, path: \"jobs/{jobId}/result\"}\n"
        "    bind: {jobId: {from: create, field: jobId}}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: success}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    api = FakeApi(responses={
        ("POST", "jobs"): {"status": 200, "json": {"success": True, "data": {"jobId": 7}}},
        ("GET", "jobs/7/result"): {"status": 200, "json": {"success": True, "data": {"result": "ok"}}},
    })
    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert res.passed
    assert len(res.steps) == 2
    assert res.steps[1].step_id == "fetch"
    assert res.steps[1].status == PASSED
    assert any(c.step == "fetch" and c.check == "success" and c.ok for c in res.checks)
    # binding resolved the path from create's response — verified via recording identity:
    assert any(r.bound_logical_path == "jobs/7/result" for r in res.provider_recordings)
    assert ("GET", "jobs/7/result") in {(r.request.method, r.request.path) for r in res.provider_recordings}


def test_backend_fail_fast_blocks_later_steps(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(
        "version: 2\n"
        "scenario: flow\ngrid: {level: r, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: a\n"
        "    request: {method: POST, path: jobs}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: has, field: jobId}\n"
        "  - id: b\n"
        "    request: {method: GET, path: other}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: success}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    api = FakeApi(responses={
        # step a's response is missing jobId -> has check fails
        ("POST", "jobs"): {"status": 200, "json": {"success": True, "data": {}}},
        ("GET", "other"): {"status": 200, "json": {"success": True}},
    })
    recorder = FakeRecorder()
    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=recorder,
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert not res.passed
    assert res.steps[0].status == FAILED
    assert res.steps[1].status == BLOCKED
    # step b's request was never sent/recorded:
    assert not any(r.request.path == "other" for r in recorder.responses())


def test_backend_option_b_guard_rejects_overridden_body_field(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(
        "version: 2\n"
        "scenario: flow\ngrid: {level: r, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: create\n"
        "    request: {method: POST, path: jobs, body: {job: original}}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: success}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    api = FakeApi(responses={("POST", "jobs"): {"status": 200, "json": {"success": True}}})

    def overriding_resolver(scenario, step, template):
        spec = ports.RequestSpec(method=template.method, path=template.path,
                                 body=dict(template.body or {}))
        spec.body["job"] = "overridden"   # violates Option B: overrides a declared field
        return spec

    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=FakeRecorder(),
                      resolve_request=overriding_resolver, normalizer=FakeNormalizer())
    assert not res.passed
    assert res.steps[0].status == ERROR


# --- Poll-step behavior: response stop condition, per-attempt trace ids, FAIL/SKIP ---

class CountingApi(ports.ApiDriver):
    """Product-neutral fake whose response for a given (method, path) varies by
    the call count — the last entry in the sequence repeats once exhausted.
    Lets a poll's readiness depend on attempt number without any real waiting."""
    def __init__(self, sequences):
        self.sequences = sequences   # {(method, path): [cfg, cfg, ...]}
        self.calls = {}
        self.sent = []

    def send(self, spec, session):
        key = (spec.method, spec.path)
        idx = self.calls.get(key, 0)
        self.calls[key] = idx + 1
        seq = self.sequences.get(key, [{"status": 200, "json": {"success": True}}])
        cfg = seq[min(idx, len(seq) - 1)]
        self.sent.append(spec)
        trace_id = spec.traceparent.split("-")[1] if spec.traceparent else None
        return ports.RecordedResponse(
            status=cfg.get("status", 200), headers=cfg.get("headers", {}),
            json=copy.deepcopy(cfg.get("json")), text=cfg.get("text", ""),
            trace_id=trace_id, request=spec)


_POLL_FLOW_YAML = (
    "version: 2\n"
    "scenario: poll_flow\ngrid: {{level: r, module: m}}\nactor: a\n"
    "steps:\n"
    "  - id: poll\n"
    "    request: {{method: GET, path: jobs/1/result}}\n"
    "    poll: {{on_timeout: {on_timeout}}}\n"
    "    expect:\n"
    "      response:\n"
    "        - {{check: has, field: result}}\n"
    "  - id: after\n"
    "    request: {{method: GET, path: other}}\n"
    "    expect:\n"
    "      response:\n"
    "        - {{check: success}}\n"
)


def test_poll_step_succeeds_on_second_attempt_with_distinct_traceparents(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(_POLL_FLOW_YAML.format(on_timeout="FAIL"), encoding="utf-8")
    s = load_scenario(str(y))
    api = CountingApi({
        ("GET", "jobs/1/result"): [
            {"status": 200, "json": {"success": True, "data": {}}},               # attempt 1: not ready
            {"status": 200, "json": {"success": True, "data": {"result": "ok"}}},  # attempt 2: ready
        ],
        ("GET", "other"): [{"status": 200, "json": {"success": True}}],
    })
    clock = FakeClock()
    recorder = FakeRecorder()
    poll_config = types.SimpleNamespace(timeout=30, interval=1)
    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=recorder,
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)

    assert res.passed
    assert res.steps[0].status == PASSED
    assert res.steps[0].attempts >= 2
    assert res.steps[1].status == PASSED   # the following step ran

    poll_recordings = [r for r in recorder.responses() if r.step_id == "poll"]
    assert len(poll_recordings) >= 2
    trace_ids = {r.trace_id for r in poll_recordings}
    assert len(trace_ids) == len(poll_recordings)   # every attempt got a distinct traceparent
    # the recorded REQUEST identity per attempt must also be distinct — each attempt
    # must carry its own RequestSpec, not a shared/mutated one (otherwise every
    # earlier recording's request.traceparent would collapse to the last attempt's):
    request_traceparents = {r.request.traceparent for r in poll_recordings}
    assert len(request_traceparents) == len(poll_recordings)
    # only the winning (final) attempt is marked final:
    assert sum(1 for r in poll_recordings if r.is_final) == 1


def test_poll_step_skip_timeout_degrades_domain(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(_POLL_FLOW_YAML.format(on_timeout="SKIP"), encoding="utf-8")
    s = load_scenario(str(y))
    api = CountingApi({
        ("GET", "jobs/1/result"): [{"status": 200, "json": {"success": True, "data": {}}}],
        ("GET", "other"): [{"status": 200, "json": {"success": True}}],
    })
    clock = FakeClock()
    poll_config = types.SimpleNamespace(timeout=3, interval=1)
    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)

    assert res.steps[0].status == SKIPPED
    assert res.steps[0].skipped == ["poll timed out (SKIP)"]
    assert res.steps[1].status == BLOCKED
    assert res.status == DEGRADED
    assert res.passed   # DEGRADED still counts as passed — nothing asserted false


def test_poll_step_fail_timeout_fails_domain(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(_POLL_FLOW_YAML.format(on_timeout="FAIL"), encoding="utf-8")
    s = load_scenario(str(y))
    api = CountingApi({
        ("GET", "jobs/1/result"): [{"status": 200, "json": {"success": True, "data": {}}}],
        ("GET", "other"): [{"status": 200, "json": {"success": True}}],
    })
    clock = FakeClock()
    poll_config = types.SimpleNamespace(timeout=3, interval=1)
    res = backend.run(s, auth=FakeAuth(), api=api, state=None, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)

    assert res.steps[0].status == FAILED
    assert any(c.check == "has" and not c.ok for c in res.steps[0].checks)
    assert res.steps[1].status == BLOCKED
    assert not res.passed


# --- State polling remains independent from business poll timing; PollConfig validation ---

def test_state_poll_uses_own_default_timeout_not_poll_config_non_poll_step(tmp_path):
    """Backend-state observation uses its own default window rather than the business poll configuration for non-poll steps."""
    y = tmp_path / "s.yaml"
    y.write_text(
        "scenario: x\ngrid: {level: smoke, module: m}\nactor: a\n"
        "precondition: []\ninputs: []\nintent: t\n"
        "expect:\n  request:\n    - {check: request, method: POST, path: p}\n"
        "  backend_state:\n    - {check: span_exists, span: dataset.import}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    clock = FakeClock()
    calls = {"n": 0}

    def observe(tid):
        calls["n"] += 1
        ready = calls["n"] >= 5   # ready only after ~4 sleeps (simulated t=4s)
        return ports.StateFacts(tid, [ports.Span("dataset.import")] if ready else [])

    state = FakeStateProbe()
    state.observe = observe
    poll_config = PollConfig(timeout=2, interval=1)   # tiny business-poll timeout
    res = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)
    assert res.passed
    assert any(c.check == "span_exists" and c.ok for c in res.checks)
    assert calls["n"] >= 5


def test_state_poll_uses_own_default_timeout_not_poll_config_poll_step(tmp_path):
    """Backend-state observation also keeps its own default window for poll steps."""
    y = tmp_path / "s.yaml"
    y.write_text(
        "version: 2\n"
        "scenario: poll_flow\ngrid: {level: r, module: m}\nactor: a\n"
        "steps:\n"
        "  - id: poll\n"
        "    request: {method: GET, path: jobs/1/result}\n"
        "    poll: {on_timeout: FAIL}\n"
        "    expect:\n"
        "      response:\n"
        "        - {check: success}\n"
        "      backend_state:\n"
        "        - {check: span_exists, span: dataset.import}\n",
        encoding="utf-8")
    s = load_scenario(str(y))
    api = FakeApi(responses={("GET", "jobs/1/result"): {"status": 200, "json": {"success": True}}})
    clock = FakeClock()
    calls = {"n": 0}

    def observe(tid):
        calls["n"] += 1
        ready = calls["n"] >= 5   # ready only after ~4 sleeps (simulated t=4s)
        return ports.StateFacts(tid, [ports.Span("dataset.import")] if ready else [])

    state = FakeStateProbe()
    state.observe = observe
    poll_config = PollConfig(timeout=2, interval=1)   # tiny business-poll timeout; response
                                                       # succeeds on attempt 1, so this timeout
                                                       # never even gets exercised by the response
                                                       # poll — it must also not leak into the
                                                       # state wait that follows.
    res = backend.run(s, auth=FakeAuth(), api=api, state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer(),
                      poll_config=poll_config, now=clock.now, sleep=clock.sleep)
    assert res.passed
    assert any(c.check == "span_exists" and c.ok for c in res.checks)
    assert calls["n"] >= 5


def test_pollconfig_rejects_nonpositive_timeout():
    with pytest.raises(ValueError):
        PollConfig(timeout=0, interval=1)


def test_pollconfig_rejects_nonpositive_interval():
    with pytest.raises(ValueError):
        PollConfig(timeout=10, interval=0)


def test_pollconfig_rejects_interval_greater_than_timeout():
    with pytest.raises(ValueError):
        PollConfig(timeout=1, interval=2)


def test_span_attr_type_mismatch_is_failed_not_error(tmp_path):
    """Problem C regression: a span_attr comparison against a type-mismatched observed
    value (e.g. a string row_count compared with `>` against an int) must surface as a
    content FAILED check with a 'cannot be compared' detail, not escape as a TypeError
    that the outer except turns into ERROR."""
    y = tmp_path / "s.yaml"
    y.write_text(_SPAN_ATTR_YAML, encoding="utf-8")
    s = load_scenario(str(y))
    state = FakeStateProbe()
    state.observe = lambda tid: ports.StateFacts(tid, [ports.Span("dataset.import", {"row_count": "3"})])
    res = backend.run(s, auth=FakeAuth(), api=FakeApi(), state=state, recorder=FakeRecorder(),
                      resolve_request=_resolver, normalizer=FakeNormalizer())
    assert res.steps[0].status == FAILED
    assert not res.passed
    failing = [c for c in res.checks if c.check == "span_attr" and not c.ok]
    assert len(failing) == 1
    assert "cannot be compared" in failing[0].detail
