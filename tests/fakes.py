"""In-memory fakes for offline core tests.

These helpers exercise the framework without network or product-specific
runtime dependencies.
"""
import copy

from refracto import ports


def _trace_id_of(traceparent):
    return traceparent.split("-")[1] if traceparent else None


class FakeAuth(ports.Authenticator):
    def session(self, role):
        return {"role": role}


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


class FakeUi(ports.UiDriver):
    def __init__(self, rendered=None, outgoing=None, recorded=None):
        self._rendered = rendered or {}
        self._outgoing = outgoing or []
        self._recorded = recorded or []

    def run_intent(self, scenario, session=None, mock=None):
        return ports.UiResult(
            rendered=dict(self._rendered),
            outgoing=list(self._outgoing),
            recorded=list(self._recorded),
        )


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

    def synthesize(self, fields, values=None) -> dict:
        values = values or {}
        return {
            "success": True,
            "error": None,
            "data": {f: values.get(f, f"<stub:{f}>") for f in fields},
        }
