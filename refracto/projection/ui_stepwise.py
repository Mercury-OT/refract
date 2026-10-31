"""The single primitive-action loop for frontend mock and live e2e.

Action completion and evidence are distinct. An adapter must identify traffic
at its origin; order, a time window, and a matching URL are not attribution.
"""
import copy
import dataclasses
import hashlib
import hmac
import json
import ipaddress
import re
import secrets
import time
from urllib.parse import urlsplit

from refracto import asyncwait, ports
from refracto import headers as header_ops
from refracto.projection.recording import _evidence_equal
from refracto.query import wire_query, require_wire_query, request_path
from refracto.declaration import binding, values
from refracto.declaration.run_values import ensure_bound_run_values
from refracto.projection import backend as backend_proj
from refracto.projection.continuation import FlowState
from refracto.projection.sessions import SessionManager
from refracto.report import (
    BLOCKED, COMPLETED, ERROR, FAILED, PASSED, SKIPPED,
    DomainResult, StepResult,
)


def _strict_equal(actual, expected):
    return values.equal(actual, expected)


def _subset(actual, expected):
    """Typed recursive map subset; arrays retain exact length and order."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return all(k in actual and _subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _subset(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected


def _require_equal(name, actual, expected):
    if not _strict_equal(actual, expected):
        raise ValueError(f"UI evidence {name} mismatch")


def _request_values_equal(actual, expected):
    return type(actual) is ports.RequestSpec and type(expected) is ports.RequestSpec and all(
        _evidence_equal(getattr(actual, item.name), getattr(expected, item.name))
        for item in dataclasses.fields(ports.RequestSpec)
    )


def _recording_values_equal(actual, expected):
    return type(actual) is ports.RecordedResponse and type(expected) is ports.RecordedResponse and all(
        _request_values_equal(actual.request, expected.request) if f.name == "request"
        else _network_values_equal(actual.browser_identity, expected.browser_identity) if f.name == "browser_identity"
        else _evidence_equal(getattr(actual, f.name), getattr(expected, f.name))
        for f in dataclasses.fields(ports.RecordedResponse)
    )


def _network_values_equal(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    return type(actual) is type(expected) is ports.BrowserNetworkIdentity and all(
        _evidence_equal(getattr(actual, name), getattr(expected, name))
        for name in ("origin", "request_id"))


def _network_key(identity, context_id):
    """Validate transport provenance without importing the browser collector."""
    if type(identity) is not ports.BrowserNetworkIdentity:
        raise TypeError("browser network identity must be BrowserNetworkIdentity")
    if type(identity.request_id) is not str or not identity.request_id.strip():
        raise ValueError("browser network request identity is required")
    origin = identity.origin
    try:
        if type(origin) is not str or any(ord(c) < 33 or ord(c) > 126 for c in origin):
            raise ValueError()
        parsed = urlsplit(origin)
        host = parsed.hostname
        if (parsed.scheme not in {"http", "https"} or not host or host.endswith(".")
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError()
        if ":" in host:
            host = "[" + ipaddress.IPv6Address(host).compressed + "]"
        elif re.fullmatch(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)*", host) is None:
            raise ValueError()
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        suffix = "" if port in (None, 443 if parsed.scheme == "https" else 80) else f":{port}"
        if origin != f"{parsed.scheme}://{host}{suffix}":
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("browser network origin must be canonical HTTP(S)") from None
    # Chromium network IDs are context-local. Origin is intentionally not part
    # of the key: changing a claimed origin must not make a replay look new.
    return ("browser-network", context_id, identity.request_id)


def _native_trace(request, response):
    """A native correlation ID must never stand in for absent wire trace data."""
    observed = [value for name, value in header_ops.require_header_items(response.request_header_items)
                if name.lower() == "traceparent"]
    if request.traceparent is None and response.trace_id is None:
        if observed:
            raise ValueError("native trace evidence was omitted")
        return False
    if observed != [request.traceparent]:
        raise ValueError("native trace does not match observed request headers")
    if (type(request.traceparent) is not str or type(response.trace_id) is not str
            or not request.traceparent or not response.trace_id):
        raise ValueError("native request/response trace is incomplete")
    parts = request.traceparent.split("-")
    if len(parts) != 4 or parts[1] != response.trace_id:
        raise ValueError("native request/response trace mismatch")
    return True


def _signature_payload(data):
    return json.dumps(
        [data[k] for k in ("execution_id", "action_id", "step_id", "mode", "action", "target", "value", "object_id",
                           "user", "session_generation", "context_id")],
        ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True,
    ).encode()


def _issue_permit(secret, execution_id, step, mode, lease, context_id):
    data = dict(execution_id=execution_id, action_id=secrets.token_hex(16),
                step_id=step.id, mode=mode, action=step.action,
                target=step.target, value=copy.deepcopy(step.value), object_id=copy.deepcopy(step.object_id),
                user=lease.user,
                session_generation=lease.generation, context_id=context_id)
    return ports.UiActionPermit(
        **data, token=hmac.new(secret, _signature_payload(data), hashlib.sha256).hexdigest(),
    )


def _validate_mock_plan(plan):
    if not isinstance(plan, list):
        raise ValueError("frontend requires an explicit mock_plan (an empty list is allowed)")
    identifiers = set()
    for item in plan:
        if type(item) is not ports.MockResponse:
            raise TypeError("mock_plan items must be MockResponse")
        if not all(type(v) is str and v for v in (item.fixture_id, item.source, item.method, item.path)):
            raise ValueError("mock fixture identity, source, method and path must be nonempty strings")
        if item.fixture_id in identifiers:
            raise ValueError("duplicate mock fixture identity")
        identifiers.add(item.fixture_id)
        if type(item.status) is not int or not 100 <= item.status <= 599 or type(item.response) is not dict:
            raise ValueError("invalid mock fixture response")
        request_path(item.path, {})
        if item.query is not None:
            require_wire_query(item.query)
        for mapping in (item.request_headers, item.response_headers):
            if mapping is not None:
                header_ops.header_map(mapping)


def _validate_rendered(rendered):
    if type(rendered) is not dict:
        raise TypeError("rendered must be an anchor mapping")
    for anchor, value in rendered.items():
        if type(anchor) is not str or type(value) is not dict:
            raise TypeError("invalid rendered anchor")
        for kind in ("identified", "anonymous"):
            objects = value.get(kind, [])
            if type(objects) is not list:
                raise TypeError("rendered objects must be lists")
            for obj in objects:
                if type(obj) is not dict or type(obj.get("fields")) is not dict:
                    raise TypeError("rendered object fields must be a mapping")
                if kind == "identified" and (type(obj.get("id")) is not str or not obj["id"]):
                    raise TypeError("identified object requires a nonempty string ID")


def _validate_diagnostic_identity(value, accepted, name):
    # Uncorrelated diagnostics may omit an identity, but cannot disguise an
    # already accepted identity or exploit Python's bool/int equality rules.
    if value is None:
        return
    if type(value) is not str or not value:
        raise TypeError(f"diagnostic {name} must be a nonempty string or None")
    if value in accepted:
        raise ValueError(f"unassigned diagnostic reused accepted {name}")


def _validate_diagnostic_request(request, accepted_traces):
    if type(request) is not ports.RequestSpec:
        raise TypeError("invalid diagnostic request")
    require_wire_query(request.query)
    request_path(request.path, {})
    parent = request.traceparent
    if parent is None:
        return
    if type(parent) is not str:
        raise TypeError("diagnostic traceparent must be a string or None")
    parts = parent.split("-")
    if len(parts) != 4 or not all(parts):
        raise ValueError("invalid diagnostic traceparent")
    _validate_diagnostic_identity(parts[1], accepted_traces, "trace")


def _has_returned_headers(result):
    """Recognize sensitive returned blocks before validating their evidence.

    Later lifecycle callbacks may retain even rejected observations. Inspect
    only the known port containers; ordinary validation still owns their shape.
    """
    if type(result) is not ports.UiActionResult or type(result.evidence) is not ports.UiActionEvidence:
        return False
    evidence = result.evidence
    responses = ([item.response for item in evidence.traffic if type(item) is ports.UiTraffic]
                 if type(evidence.traffic) is list else [])
    for items in (evidence.diagnostic_recorded, evidence.mock_recordings):
        if type(items) is list:
            responses.extend(items)
    return any(header_ops.recorded(response) for response in responses
               if type(response) is ports.RecordedResponse)


def _validate_evidence(result, permit, secret, accepted_tokens, seen_requests, seen_traces,
                       mock_plan, consumed):
    if type(result) is not ports.UiActionResult:
        raise TypeError("perform_step must return UiActionResult")
    data = {k: getattr(permit, k) for k in (
        "execution_id", "action_id", "step_id", "mode", "action", "target", "value", "object_id",
        "user", "session_generation", "context_id")}
    signed = hmac.new(secret, _signature_payload(data), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(permit.token, signed):
        raise ValueError("action permit was modified")
    if result.evidence is None:
        if permit.object_id is not None:
            raise ValueError("scoped UI action requires object selection evidence")
        return None
    evidence = result.evidence
    if type(evidence) is not ports.UiActionEvidence:
        raise TypeError("action evidence must be UiActionEvidence")
    for name in ("execution_id", "action_id", "step_id", "mode", "user", "session_generation", "context_id"):
        _require_equal(name, getattr(evidence, name), getattr(permit, name))
    if evidence.permit_token in accepted_tokens:
        raise ValueError("replayed action evidence")
    _require_equal("permit token", evidence.permit_token, permit.token)
    selection = evidence.object_selection
    if permit.object_id is None:
        if selection is not None:
            raise ValueError("unscoped UI action must not claim object selection")
    else:
        if type(selection) is not ports.UiObjectSelection:
            raise TypeError("scoped UI action requires UiObjectSelection")
        _require_equal("selected object", selection.object_id, permit.object_id)
        if any(type(count) is not int or count != 1
               for count in (selection.object_matches, selection.control_matches)):
            raise ValueError("UI object and control selection must both be unique")
    if type(evidence.traffic) is not list:
        raise TypeError("rendered and traffic must be dict/list")
    if (type(evidence.diagnostic_notes) is not list or any(
            type(note) is not str or note not in {
                "background diagnostics truncated", "background HTTP acquisition failed"}
            for note in evidence.diagnostic_notes)
            or len(evidence.diagnostic_notes) > 2
            or len(set(evidence.diagnostic_notes)) != len(evidence.diagnostic_notes)):
        raise ValueError("unsupported browser diagnostic note")
    _validate_rendered(evidence.rendered)
    local_requests, local_traces = set(), set()
    for traffic in evidence.traffic:
        if type(traffic) is not ports.UiTraffic:
            raise TypeError("traffic must contain UiTraffic")
        for name in ("execution_id", "action_id", "step_id", "mode", "user", "session_generation", "context_id"):
            _require_equal(f"traffic {name}", getattr(traffic, name), getattr(permit, name))
        _require_equal("traffic permit token", traffic.permit_token, permit.token)
        if type(traffic.request_id) is not str or not traffic.request_id:
            raise ValueError("request identity is required")
        if traffic.request_id in seen_requests | local_requests:
            raise ValueError("replayed request identity")
        local_requests.add(traffic.request_id)
        req, resp = traffic.request, traffic.response
        if type(req) is not ports.RequestSpec or type(resp) is not ports.RecordedResponse:
            raise TypeError("traffic must pair RequestSpec and RecordedResponse")
        require_wire_query(req.query)
        request_path(req.path, {})
        if not _request_values_equal(req, resp.request):
            raise ValueError("request/response pairing mismatch")
        _require_equal("request identity pairing", resp.request_id, traffic.request_id)
        native = traffic.browser_identity is not None or resp.browser_identity is not None
        if native:
            key = _network_key(traffic.browser_identity, permit.context_id)
            _network_key(resp.browser_identity, permit.context_id)
            if not _network_values_equal(traffic.browser_identity, resp.browser_identity):
                raise ValueError("browser network identity pairing mismatch")
            if key in seen_requests | local_requests:
                raise ValueError("replayed browser network identity")
            local_requests.add(key)
        if not all(type(v) is str and v for v in (req.method, req.path)):
            raise ValueError("traffic transport identity is required")
        if not native or _native_trace(req, resp):
            if not all(type(v) is str and v for v in (req.traceparent, resp.trace_id)):
                raise ValueError("traffic trace identity is required")
            parts = req.traceparent.split("-")
            if len(parts) != 4 or parts[1] != resp.trace_id:
                raise ValueError("request/response trace mismatch")
            if resp.trace_id in seen_traces | local_traces:
                raise ValueError("replayed request trace")
            local_traces.add(resp.trace_id)
        _require_equal("recording step", resp.step_id, permit.step_id)
        _require_equal("recording attempt", resp.attempt_index, 0)
        _require_equal("recording final", resp.is_final, True)
        _require_equal("recording user", resp.user, permit.user)
        _require_equal("recording session generation", resp.session_generation, permit.session_generation)
        if type(resp.actual_path) is not str or not resp.actual_path:
            raise ValueError("recording actual_path is required")
        if permit.mode == "mock":
            _require_equal("mock response fixture pairing", resp.mock_fixture_id, traffic.mock_fixture_id)
        elif traffic.mock_fixture_id is not None or resp.mock_fixture_id is not None:
            raise ValueError("live traffic cannot carry mock evidence")
    if type(evidence.diagnostic_outgoing) is not list or type(evidence.diagnostic_recorded) is not list:
        raise TypeError("diagnostics must be lists")
    accepted_requests = seen_requests | local_requests
    accepted_traces = seen_traces | local_traces
    for req in evidence.diagnostic_outgoing:
        _validate_diagnostic_request(req, accepted_traces)
    for resp in evidence.diagnostic_recorded:
        if type(resp) is not ports.RecordedResponse:
            raise TypeError("invalid diagnostic response")
        _validate_diagnostic_identity(resp.request_id, accepted_requests, "request identity")
        _validate_diagnostic_identity(resp.trace_id, accepted_traces, "trace")
        _validate_diagnostic_request(resp.request, accepted_traces)
        if resp.browser_identity is not None:
            key = _network_key(resp.browser_identity, permit.context_id)
            if key in accepted_requests:
                raise ValueError("diagnostic reused browser network identity")
            _native_trace(resp.request, resp)
            accepted_requests.add(key)
            local_requests.add(key)
    local_consumption = []
    if permit.mode == "mock":
        if type(evidence.mock_recordings) is not list:
            raise TypeError("mock_recordings must be an ordered list")
        provided = [t.response for t in evidence.traffic] + evidence.diagnostic_recorded
        if len(provided) != len(evidence.mock_recordings):
            raise ValueError("mock consumption omitted or duplicated traffic")
        ids = [r.request_id for r in evidence.mock_recordings]
        if any(type(i) is not str or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("invalid mock request identity")
        for response in evidence.mock_recordings:
            if sum(_recording_values_equal(response, r) for r in provided) != 1:
                raise ValueError("mock consumption response differs from evidence")
            index = len(consumed) + len(local_consumption)
            if index >= len(mock_plan):
                raise ValueError("mock plan exhausted")
            fixture = mock_plan[index]
            for name, actual, expected in (
                ("fixture identity", response.mock_fixture_id, fixture.fixture_id),
                ("fixture method", response.request.method, fixture.method),
                ("fixture path", response.request.path, fixture.path),
                ("fixture status", response.status, fixture.status),
                ("fixture response", response.json, fixture.response),
            ):
                _require_equal(name, actual, expected)
            if fixture.query is not None:
                _require_equal("fixture query", response.request.query, fixture.query)
            for expected, observed in ((fixture.request_headers, response.request_header_items),
                                       (fixture.response_headers, response.header_items)):
                if expected is not None:
                    header_ops.require_header_items(observed)
                    if not header_ops.match_headers(expected, observed):
                        raise ValueError("mock fixture header evidence differs from supplied fixture")
            local_consumption.append(dict(fixture_id=fixture.fixture_id, source=fixture.source,
                                          step_id=permit.step_id, request_id=response.request_id))
    elif evidence.mock_recordings:
        raise ValueError("live evidence cannot contain mock recordings")
    accepted_tokens.add(permit.token)
    seen_requests.update(local_requests)
    seen_traces.update(local_traces)
    consumed.extend(local_consumption)
    return evidence


def _record_verified_primary(recorder, response, expected_recordings):
    if recorder is None:
        raise ValueError("e2e live execution requires a Recorder")
    expected = copy.deepcopy(response)
    sensitive = header_ops.recorded(expected) or any(header_ops.recorded(item) for item in expected_recordings)
    header_ops.call_port("Recorder", recorder.record, copy.deepcopy(expected), sensitive=sensitive)
    observed = header_ops.call_port("Recorder", recorder.responses, sensitive=sensitive)
    wanted = [*expected_recordings, expected]
    if type(observed) is not list or len(observed) != len(wanted):
        raise ValueError("Recorder response count mismatch")
    if not all(_recording_values_equal(a, b) for a, b in zip(observed, wanted)):
        raise ValueError("Recorder identity/order mismatch")
    return copy.deepcopy(observed)


def _validate_state_facts(facts, trace_id):
    if type(facts) is not ports.StateFacts:
        raise TypeError("StateProbe.observe must return StateFacts")
    _require_equal("state trace", facts.trace_id, trace_id)
    return facts


class _VerifiedRecorder:
    """Keep the existing Recorder seam, checking each append and every read."""
    def __init__(self, recorder, expected):
        self.recorder, self.expected = recorder, expected

    def record(self, response):
        verified = _record_verified_primary(self.recorder, response, self.expected)
        self.expected[:] = verified

    def responses(self):
        observed = header_ops.call_port("Recorder", self.recorder.responses,
            sensitive=any(header_ops.recorded(item) for item in self.expected))
        if type(observed) is not list or len(observed) != len(self.expected):
            raise ValueError("Recorder response count mismatch")
        if not all(_recording_values_equal(a, b) for a, b in zip(observed, self.expected)):
            raise ValueError("Recorder identity/order mismatch")
        return copy.deepcopy(observed)


class _VerifiedState:
    def __init__(self, state):
        self.state = state

    def observe(self, trace_id):
        return _validate_state_facts(self.state.observe(trace_id), trace_id)


class _VerifiedApi:
    def __init__(self, api):
        self.api = api

    def send(self, request, session):
        expected = copy.deepcopy(request)
        response = self.api.send(copy.deepcopy(expected), session)
        if type(response) is not ports.RecordedResponse:
            raise TypeError("ApiDriver.send must return RecordedResponse")
        if not _request_values_equal(response.request, expected):
            raise ValueError("API request/response pairing mismatch")
        request_trace = expected.traceparent.split("-")[1]
        if response.trace_id is not None:
            _require_equal("API response trace", response.trace_id, request_trace)
        protected = copy.deepcopy(response)
        # A paired local API response need not claim server trace observation.
        # This is the outbound request's correlation context, not server proof;
        # StateProbe must still independently observe facts for this trace.
        protected.trace_id = request_trace
        protected.request_id = secrets.token_hex(16)
        return protected


def _assert_live_backend_state_for(step, state, trace_id, *, state_timeout=30,
                                  interval=1, now=None, sleep=None,
                                  bound_values=None, inputs=None):
    span_assertions = [a for a in step.expect.backend_state
                       if a.check != "object_field_equals"]
    if not span_assertions:
        return [], []
    if state is None:
        return [], ["declared backend_state unavailable: no StateProbe"]
    if type(trace_id) is not str or not trace_id:
        raise ValueError("state requires current selected request trace")
    def observe():
        facts = _validate_state_facts(state.observe(trace_id), trace_id)
        return all(backend_proj._eval_span(a, facts, bound_values, inputs).ok
                   for a in span_assertions), facts
    try:
        facts = asyncwait.wait_until(observe, timeout=state_timeout, interval=interval,
                                    on_timeout=asyncwait.FAIL, now=now, sleep=sleep).value
    except asyncwait.WaitTimeout:
        facts = _validate_state_facts(state.observe(trace_id), trace_id)
    return [backend_proj._eval_span(a, facts, bound_values, inputs)
            for a in span_assertions], []


def _before_context_error(scenario, projection, exc):
    first, *rest = scenario.steps
    return DomainResult(projection=projection, steps=[
        StepResult(first.id, ERROR, detail=str(exc), user=scenario.effective_user(first)),
        *(StepResult(s.id, BLOCKED, detail="a prior step stopped the flow", blocked_by=[first.id],
                     user=scenario.effective_user(s)) for s in rest),
    ])


def run(scenario, *, ui, normalizer, auth, eval_frontend, eval_request_shape,
        projection="frontend", mode="mock", eval_response=None, state=None,
        recorder=None, api=None, resolve_request=None, poll_config=None,
        mock_plan=None, now=None, sleep=None, object_state=None):
    """No legacy path: every Scenario uses this one action/expectation loop."""
    needs_ui = any(s.action in {"open", "click", "fill"} or s.expect.frontend
                   for s in scenario.steps)
    try:
        ensure_bound_run_values(scenario)
        sessions = SessionManager(scenario, auth)
        sessions.preflight()
        if needs_ui and (not isinstance(ui, ports.StepwiseUiDriver)
                         or ui.supports_stepwise_mode(mode) is not True):
            raise ValueError("primitive UI capability not supported")
        if any(step.object_id is not None for step in scenario.steps):
            if (not isinstance(ui, ports.StepwiseUiDriver) or backend_proj._call_action_port(
                    "UI object targeting", ui.supports_object_targeting, mode) is not True):
                raise ValueError("UI object targeting capability not supported")
        if mode == "mock":
            _validate_mock_plan(mock_plan)
        for step in scenario.steps:
            if step.action == "request" and mode == "mock":
                raise ValueError("frontend direct API actions are not supported")
            if step.action == "request" and (api is None or resolve_request is None):
                raise ValueError("explicit API action requires ApiDriver and request mapping")
            if step.action == "request" and step.expect.frontend:
                raise ValueError("direct API action with UI assertions is not supported")
            if step.expect.backend_state and step.request is None:
                raise ValueError("requestless state observation has no correlation source")
            if step.poll is not None and step.action != "request":
                raise ValueError("polling UI actions is not supported")
            if step.action == "wait" and step.request is not None:
                raise ValueError("wait cannot claim request evidence without an action origin")
    except Exception as exc:
        return _before_context_error(scenario, projection, exc)

    secret, execution_id = secrets.token_bytes(32), secrets.token_hex(16)
    accepted_tokens, seen_requests, seen_traces = set(), set(), set()
    retained_plan = copy.deepcopy(mock_plan) if mode == "mock" else None
    sensitive_headers = (any(header_ops.declared(item) for item in scenario.steps)
        or any(item.request_headers is not None or item.response_headers is not None
               for item in (retained_plan or [])))
    consumed, results, recordings, prior = [], [], [], {}
    flow = FlowState()
    contexts = {}
    mock_queue = ports.MockResponseQueue(copy.deepcopy(retained_plan)) if mode == "mock" else None

    def close_user(user):
        # Remove before calling the adapter so a failed close is never retried.
        existing = contexts.pop(user, None)
        if existing is not None:
            header_ops.call_port("UI close", ui.close_stepwise, existing[0], sensitive=sensitive_headers)

    def context_for(lease):
        existing = contexts.get(lease.user)
        if existing is None:
            identity = secrets.token_hex(16)
            context = backend_proj._call_action_port("UI open", ui.open_stepwise,
                lease.credentials, mode=mode,
                mock_plan=copy.deepcopy(retained_plan), mock_queue=mock_queue,
                user=lease.user, session_generation=lease.generation, context_id=identity)
            existing = contexts[lease.user] = (context, lease.generation, identity)
        if existing[1] != lease.generation:
            raise ValueError("UI context belongs to an obsolete session")
        return existing[0], existing[2]

    try:
        for declared in scenario.steps:
            user = scenario.effective_user(declared)
            blocked = flow.blocked(declared)
            if blocked is not None:
                blocked.user = user
                results.append(blocked)
                continue
            resolved, norm, object_selection = {}, None, None
            lease = None
            prepared_ok = False
            try:
                step, bound = binding.prepare_step(declared, scenario, prior)
                prepared_ok = True
                resolved = dict(bound)
                lease = sessions.acquire(user, new=step.session == "new")
                if step.session == "new":
                    close_user(user)
                if step.action == "request":
                    sr, norm = backend_proj.execute_api_step(
                        scenario, step, session=lease.credentials, session_lease=lease, api=_VerifiedApi(api),
                        state=_VerifiedState(state) if state is not None else None,
                        recorder=_VerifiedRecorder(recorder, recordings), resolve_request=resolve_request,
                        normalizer=normalizer, poll_config=poll_config,
                        now=now, sleep=sleep, bound_values=bound,
                        object_state=object_state, projection=projection,
                    )
                    recordings = _VerifiedRecorder(recorder, recordings).responses()
                    # API and UI share one run-level evidence namespace. This
                    # includes non-final polling responses already accepted by
                    # the verified Recorder; absent identities stay absent.
                    seen_requests.update(r.request_id for r in recordings
                                         if type(r.request_id) is str and r.request_id)
                    seen_traces.update(r.trace_id for r in recordings
                                       if type(r.trace_id) is str and r.trace_id)
                else:
                    evidence = None
                    if step.action == "wait":
                        (sleep or time.sleep)(step.duration / 1000)
                        rendered = header_ops.call_port("UI snapshot", ui.snapshot, context_for(lease)[0],
                            sensitive=sensitive_headers) if step.expect.frontend else {}
                        _validate_rendered(rendered)
                    else:
                        context, context_id = context_for(lease)
                        permit = _issue_permit(secret, execution_id, step, mode, lease, context_id)
                        business_header_names = tuple(sorted(header_ops.business_headers(
                            step.request.headers or {}))) if step.request is not None else ()
                        outcome = backend_proj._call_action_port("UI action", ui.perform_step,
                            context, permit, business_header_names=business_header_names)
                        sensitive_headers = sensitive_headers or _has_returned_headers(outcome)
                        evidence = _validate_evidence(outcome, permit, secret, accepted_tokens,
                                                      seen_requests, seen_traces, retained_plan, consumed)
                        object_selection = copy.deepcopy(evidence.object_selection) if evidence is not None else None
                        if evidence is None:
                            sr = StepResult(step.id, SKIPPED, skipped=[outcome.skip_reason])
                            sr.resolved_bindings = resolved
                            sr.user, sr.session_generation = user, lease.generation
                            flow.finish(declared, sr)
                            results.append(sr)
                            continue
                        rendered = evidence.rendered
                    checks = [eval_frontend(a, rendered, bound_values=bound, inputs=scenario.inputs)
                              for a in step.expect.frontend]
                    skipped, not_checked, trace_id = [], list(evidence.diagnostic_notes) if evidence else [], None
                    if step.request is not None:
                        matches = [t for t in evidence.traffic
                                   if t.request.method == step.request.method
                                   and t.request.path == step.request.path]
                        if len(matches) > 1 and step.request.query is not None:
                            expected_query = wire_query(step.request.query)
                            matches = [t for t in matches if t.request.query == expected_query]
                        if len(matches) > 1 and step.request.headers:
                            matches = [t for t in matches if header_ops.match_headers(
                                step.request.headers, t.response.request_header_items)]
                        if len(matches) != 1:
                            raise ValueError("declared UI request missing or ambiguous among associated traffic")
                        selected = matches[0]
                        checks.append(eval_request_shape(step.request, [selected.request],
                            request_header_items=selected.response.request_header_items))
                        protected = copy.deepcopy(selected.response)
                        protected.template_path = step.request.declared_path or declared.request.path
                        protected.bound_logical_path = step.request.path
                        observed_status = backend_proj._capture_status(step, protected)
                        observed_headers = copy.deepcopy(protected.header_items)
                        norm = backend_proj.normalize_response(normalizer, protected)
                        trace_id = protected.trace_id
                        if mode == "live":
                            recordings = _record_verified_primary(recorder, protected, recordings)
                        checks.extend(backend_proj._eval_response(a, norm, bound_values=bound,
                                                                  inputs=scenario.inputs,
                                                                  observed_status=observed_status,
                                                                  observed_headers=observed_headers)
                                      for a in step.expect.response)
                    if mode == "live":
                        extra, skipped = _assert_live_backend_state_for(
                            step, state, trace_id,
                            state_timeout=poll_config.timeout if poll_config else 30,
                            interval=poll_config.interval if poll_config else 1,
                            now=now, sleep=sleep, bound_values=bound, inputs=scenario.inputs)
                        checks.extend(extra)
                    elif step.expect.backend_state:
                        not_checked.append("backend_state is outside frontend mock scope")
                    for check in checks:
                        check.step = step.id
                    status = FAILED if any(not c.ok for c in checks) else (PASSED if checks else COMPLETED)
                    sr = StepResult(step.id, status, checks=checks, skipped=skipped,
                                    trace_id=trace_id, not_checked=not_checked)
                    if mode == "live":
                        backend_proj.apply_object_observation(
                            sr, step, object_state, projection=projection, user=user,
                            session_generation=lease.generation, bound_values=bound,
                            inputs=scenario.inputs)
            except binding.DependencyUnavailable as exc:
                sr = (StepResult(declared.id, ERROR, detail=str(exc)) if prepared_ok else
                      StepResult(declared.id, BLOCKED, detail=str(exc), blocked_by=exc.sources))
                norm = None
            except Exception as exc:
                sr = StepResult(declared.id, ERROR, detail=str(exc))
                norm = None
            sr.object_selection = object_selection
            sr.resolved_bindings = resolved
            sr.user = user
            sr.session_generation = lease.generation if lease is not None else None
            flow.finish(declared, sr, norm)
            results.append(sr)
            if norm is not None:
                prior[declared.id] = norm
    finally:
        for user in list(contexts):
            try:
                close_user(user)
            except Exception as exc:
                for sr in reversed(results):
                    if sr.status != BLOCKED:
                        sr.status, sr.detail = ERROR, f"UI context close failed: {exc}"
                        break
    return DomainResult(projection, steps=results,
                        provider_recordings=recordings if mode == "live" else [],
                        mock_consumption=consumed,
                        not_checked=["mock fixtures are not live backend evidence"] if mode == "mock" else [])
