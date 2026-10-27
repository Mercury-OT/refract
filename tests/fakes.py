"""In-memory fakes for offline core tests.

These helpers exercise the framework without network or product-specific
runtime dependencies.
"""
import copy
import dataclasses
import secrets

from refracto import ports


def _trace_id_of(traceparent):
    return traceparent.split("-")[1] if traceparent else None


class FakeAuth(ports.Authenticator):
    def identify(self, user):
        return "fake-principal:" + user

    def session(self, user):
        return ports.UserSession(principal_id=self.identify(user),
            authentication_id=secrets.token_hex(16), credentials={"user": user})


class FakeApi(ports.ApiDriver):
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.sent = []

    def send(self, spec, session):
        self.sent.append(spec)
        cfg = self.responses.get(
            (spec.method, spec.path),
            {"status": 200, "json": {"success": True}},
        )
        return ports.RecordedResponse(
            status=cfg.get("status", 200),
            headers=cfg.get("headers", {}),
            json=copy.deepcopy(cfg.get("json")),
            text=cfg.get("text", ""),
            trace_id=_trace_id_of(spec.traceparent),
            request=spec,
        )


class FakeStateProbe(ports.StateProbe):
    def __init__(self, spans_by_trace=None):
        self.spans_by_trace = spans_by_trace or {}

    def observe(self, trace_id):
        return ports.StateFacts(
            trace_id=trace_id,
            spans=list(self.spans_by_trace.get(trace_id, [])),
        )


class FakeUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, rendered=None, outgoing=None, recorded=None, scripts=None):
        self._rendered = rendered or {}
        self._outgoing = outgoing or []
        self._recorded = recorded or []
        self.scripts = scripts
        self.permits = []
        self.open_calls = self.close_calls = 0
        self.contexts = []
        self.fixture_index = 0

    def supports_stepwise_mode(self, mode):
        return mode in {"mock", "live"}

    def open_stepwise(self, session=None, *, mode, mock_plan=None,
                      mock_queue=None, user=None, session_generation=0, context_id=""):
        self.open_calls += 1
        context = {"mode": mode, "mock_plan": mock_plan or [], "mock_queue": mock_queue,
                   "user": user, "session_generation": session_generation, "context_id": context_id,
                   "session": session}
        self.contexts.append(context)
        return context

    def close_stepwise(self, context):
        self.close_calls += 1

    def snapshot(self, context):
        return copy.deepcopy(self._rendered)

    def perform_step(self, context, permit, *, business_header_names=()):
        index = len(self.permits)
        self.permits.append(permit)
        self.contexts.append(context)
        if self.scripts is not None:
            return self.scripts[index](self, context, permit)
        responses = copy.deepcopy(self._recorded)
        traffic = []
        for i, request in enumerate(self._outgoing):
            trace_id = secrets.token_hex(16)
            request = dataclasses.replace(request, traceparent=f"00-{trace_id}-{secrets.token_hex(8)}-01")
            request_id = secrets.token_hex(16)
            fixture_id = None
            if context["mode"] == "mock":
                queue = context["mock_queue"]
                fixture = queue.plan[queue.index] if queue is not None else context["mock_plan"][self.fixture_index]
                if queue is not None:
                    queue.index += 1
                self.fixture_index += 1
                fixture_id = fixture.fixture_id
                response = ports.RecordedResponse(fixture.status, {}, copy.deepcopy(fixture.response), "", trace_id, request)
            else:
                response = responses[i]
            response = dataclasses.replace(response, request=dataclasses.replace(request), trace_id=trace_id,
                                           step_id=permit.step_id, actual_path="/" + request.path,
                                           request_id=request_id, mock_fixture_id=fixture_id,
                                           user=permit.user, session_generation=permit.session_generation)
            traffic.append(ports.UiTraffic(
                execution_id=permit.execution_id, action_id=permit.action_id, step_id=permit.step_id,
                mode=permit.mode, request_id=request_id, permit_token=permit.token,
                request=request, response=response, mock_fixture_id=fixture_id,
                user=permit.user, session_generation=permit.session_generation, context_id=permit.context_id))
        return ports.UiActionResult(evidence=ports.UiActionEvidence(
            execution_id=permit.execution_id, action_id=permit.action_id, step_id=permit.step_id,
            mode=permit.mode, permit_token=permit.token, traffic=traffic,
            user=permit.user, session_generation=permit.session_generation, context_id=permit.context_id,
            rendered=copy.deepcopy(self._rendered),
            mock_recordings=[t.response for t in traffic] if permit.mode == "mock" else []))

class FakeRecorder(ports.Recorder):
    def __init__(self):
        self._responses = []

    def record(self, resp):
        self._responses.append(resp)

    def responses(self):
        return list(self._responses)


class FakeNormalizer(ports.ResponseNormalizer):
    """Simple `{success, error, data}` envelope semantics for offline tests."""

    def normalize(self, resp):
        body = resp.json if isinstance(resp.json, dict) else {}
        if body:
            succeeded = body.get("success") is True
        else:
            succeeded = 200 <= resp.status < 300
        data = body.get("data")
        if isinstance(data, dict):
            fields = dict(data)
        else:
            fields = {k: v for k, v in body.items() if k not in ("success", "error")}
        return ports.NormalizedResponse(
            succeeded=succeeded,
            fields=fields,
            status=resp.status,
            raw=resp,
        )
