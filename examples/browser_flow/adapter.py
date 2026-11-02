"""Reuse product mappings and observe the actual displayed record, without expectations."""
import json
import math

from examples.browser_multi_origin.adapter import Auth as RecordsAuth
from examples.browser_multi_origin.adapter import Normalizer, RecordsUi, TARGETS
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous displayed JSON member")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("displayed JSON must contain finite values")


def _finite_number(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("displayed JSON must contain finite values")
    return value


def read_rendered(page):
    """Map one visible #result display; missing identity remains anonymous.

    Empty text is normal before the first operation (an empty pre may have no
    visible area). Nonempty hidden, malformed or ambiguous output is unavailable
    evidence, never a matching object. Values are neither coerced nor completed.
    """
    result = page.locator("#result")
    if result.count() != 1:
        raise ValueError("expected one result display")
    text = result.inner_text()
    observations = {"identified": [], "anonymous": []}
    if not text.strip():
        # CSS can suppress innerText while textContent still contains a result.
        # Raw text is used only to reject unavailable rendering, not as evidence.
        raw_text = result.text_content()
        if raw_text is None or raw_text.strip():
            raise ValueError("result display is unavailable")
        return {"records.result": observations}
    if not result.is_visible():
        raise ValueError("result display is hidden")
    try:
        envelope = json.loads(text, object_pairs_hook=_unique_keys,
                              parse_constant=_invalid_constant, parse_float=_finite_number)
    except (ValueError, TypeError):
        raise ValueError("result display is not unambiguous JSON") from None
    if (type(envelope) is not dict or type(envelope.get("success")) is not bool
            or type(envelope.get("data")) is not dict):
        raise ValueError("unsupported displayed result shape")
    fields = envelope["data"]
    identity = fields.get("id")
    if type(identity) is str and identity:
        observations["identified"].append({"id": identity, "fields": fields})
    else:
        observations["anonymous"].append({"fields": fields})
    return {"records.result": observations}


class Auth(RecordsAuth):
    """Keep only logical-user acquisition diagnostics, never credentials."""

    def __init__(self, page_url):
        super().__init__(page_url)
        self.session_calls = []

    def session(self, user):
        session = super().session(user)
        self.session_calls.append(user)
        return session


class BrowserFlowUi(RecordsUi):
    """Use existing primitive mappings with a public DOM observation callback."""

    def __init__(self, app):
        self.page_url = app.page_url
        self.elements = {name: "#" + app.selector_prefix + name for name in TARGETS}
        policy = BrowserNetworkPolicy(
            api_endpoints=(ApiEndpoint(app.api_url, app.api_prefix, "records-api"),),
            resource_origins=(app.static_url,), credential_origins=(app.api_url,))
        self.browser = BrowserSupport(app.page_url, read_rendered, timeout_ms=5000,
                                      network_policy=policy)
        self.opened = []
        self.closed = []
        self.actions = []
        self._context_ids = {}

    def open_stepwise(self, session, *, mode, mock_plan=None, mock_queue=None,
                      user=None, session_generation=0, context_id=""):
        context = super().open_stepwise(
            session, mode=mode, mock_plan=mock_plan, mock_queue=mock_queue,
            user=user, session_generation=session_generation, context_id=context_id)
        self._context_ids[id(context)] = context_id
        self.opened.append({"user": user, "session_generation": session_generation,
                            "context_id": context_id})
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.actions.append({name: getattr(permit, name) for name in (
            "action_id", "step_id", "action", "target", "user",
            "session_generation", "context_id")})
        return super().perform_step(context, permit,
                                    business_header_names=business_header_names)

    def close_stepwise(self, context):
        super().close_stepwise(context)
        self.closed.append(self._context_ids.pop(id(context)))


def build_adapters(app):
    return Adapters(Auth(app.page_url), None, None, BrowserFlowUi(app),
                    InMemoryRecorder, None, Normalizer())
