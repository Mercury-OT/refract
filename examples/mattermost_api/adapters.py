"""Actual HTTP, explicit account sessions and lossless object normalization.

This pilot adapter is intentionally not an environment provisioner. It never
creates accounts, teams or fixtures on a Scenario's behalf.
"""

import copy
from dataclasses import dataclass, field
import http.client
import json
import math
import time
from urllib.parse import urlsplit
from uuid import uuid4

from refracto import ports, runner
from refracto.headers import business_headers
from refracto.query import request_path, wire_query
from refracto.recorder import InMemoryRecorder


_SECRET_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie", "token",
    "x-csrf-token", "x-xsrf-token",
})


def safe_headers(pairs):
    """Explicit export omission, not evidence that omitted headers were absent."""
    return [[key, value] for key, value in pairs if key.lower() not in _SECRET_HEADERS]


def single_header(pairs, name):
    values = [value for key, value in pairs if key.lower() == name.lower()]
    if len(values) != 1 or not values[0]:
        raise ValueError("required single response header is unavailable")
    return values[0]


def _pairs_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def strict_json(text):
    def invalid_constant(_):
        raise ValueError("non-finite JSON number")
    def finite_float(text):
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("non-finite JSON number")
        return number
    return json.loads(text, object_pairs_hook=_pairs_object,
                      parse_constant=invalid_constant, parse_float=finite_float)


@dataclass
class HttpObservation:
    status: int
    headers: list = field(repr=False)
    json: object = field(repr=False)
    text: str = field(repr=False)
    path: str = field(repr=False)
    duration: float
    request_header_items: list = field(default_factory=list, repr=False)


class MattermostHttp:
    """Finite loopback HTTP exchanges; no redirect following, retries or cookies."""

    def __init__(self, base_url, *, timeout=15.0, max_response_bytes=8 * 1024 * 1024):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("pilot requires an explicit loopback HTTP origin")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ValueError("response budget must be a positive integer")
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.timeout, self.max_response_bytes = timeout, max_response_bytes
        self.events = []
        self._secrets = set()

    @property
    def request_count(self):
        return len(self.events)

    @property
    def authentication_count(self):
        return sum(event["kind"] == "authentication" for event in self.events)

    def assert_export_safe(self, value):
        """Refuse exporting known credentials even if a server reflects them."""
        if isinstance(value, str):
            if any(secret in value for secret in self._secrets):
                raise ValueError("export contains a known credential")
        elif isinstance(value, dict):
            for key, item in value.items():
                self.assert_export_safe(key)
                self.assert_export_safe(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.assert_export_safe(item)

    def exchange(self, method, path, *, body=None, query=None, headers=None,
                 token=None, sensitive=False, traceparent=None):
        if method not in {"GET", "POST", "PUT", "DELETE"}:
            raise ValueError("method outside the bounded pilot")
        if (type(path) is not str or not path.startswith("/api/v4/")
                or path.startswith("//") or "\\" in path):
            raise ValueError("request must stay in the fixed API prefix")
        target = request_path(path, {} if query is None else query)
        declared = business_headers({} if headers is None else headers)
        if token is not None and (type(token) is not str or not token or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise ValueError("invalid session credential shape")
        payload = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        host = f"[{self.host}]" if ":" in self.host else self.host
        wire_headers = {"Host": f"{host}:{self.port}", "Accept": "application/json",
                        "Accept-Encoding": "identity", **declared}
        if payload is not None:
            wire_headers.update({"Content-Type": "application/json", "Content-Length": str(len(payload))})
        if token is not None:
            wire_headers["Authorization"] = "Bearer " + token
            self._secrets.add(token)
        if sensitive and isinstance(body, dict) and isinstance(body.get("password"), str):
            self._secrets.add(body["password"])
        if traceparent is not None:
            if type(traceparent) is not str or any(ord(c) < 33 or ord(c) > 126 for c in traceparent):
                raise ValueError("invalid trace header shape")
            wire_headers["Traceparent"] = traceparent
        started = time.perf_counter()
        event = {"kind": "authentication" if sensitive else "business", "method": method,
                 "status": None, "error": None}
        if not sensitive:
            event.update(path=target, request_body=copy.deepcopy(body),
                         request_headers=safe_headers(list(wire_headers.items())))
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, target, body=payload, headers=wire_headers)
            response = connection.getresponse()
            pairs = response.getheaders()
            if sensitive:
                self._secrets.update(value for key, value in pairs
                                     if key.lower() in _SECRET_HEADERS and value)
            event["status"] = response.status
            raw = response.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                raise ValueError("response exceeds the pilot byte budget")
            text = raw.decode("utf-8")
            try:
                value = strict_json(text)
            except (ValueError, json.JSONDecodeError):
                value = None
            if not sensitive:
                event.update(response_headers=safe_headers(pairs), response_body=copy.deepcopy(value),
                             response_text=text)
            return HttpObservation(response.status, pairs, value, text, target,
                                   time.perf_counter() - started, list(wire_headers.items()))
        except Exception as exc:
            event["error"] = next((name for cls, name in (
                (TimeoutError, "timeout"), (ConnectionError, "connection"),
                (OSError, "transport"), (ValueError, "invalid_response"),
            ) if isinstance(exc, cls)), "transport")
            raise
        finally:
            connection.close()
            event["duration_seconds"] = time.perf_counter() - started
            self.events.append(event)


class MattermostAuthenticator(ports.Authenticator):
    def __init__(self, client, accounts):
        if type(accounts) is not dict or set(accounts) != {"owner", "peer"}:
            raise ValueError("pilot requires exactly owner and peer account mappings")
        self._client, self._accounts = client, copy.deepcopy(accounts)
        principals = []
        for account in self._accounts.values():
            if type(account) is not dict or set(account) != {"id", "login_id", "password"}:
                raise ValueError("account mapping has invalid fields")
            if any(type(account[key]) is not str or not account[key] for key in account):
                raise ValueError("account mapping contains unavailable values")
            principals.append(account["id"])
        if len(set(principals)) != len(principals):
            raise ValueError("named users must map to distinct accounts")
        self.session_events = []

    def identify(self, user):
        return self._accounts[user]["id"]

    def session(self, user):
        account = self._accounts[user]
        result = self._client.exchange("POST", "/api/v4/users/login",
            body={"login_id": account["login_id"], "password": account["password"]}, sensitive=True)
        if (result.status != 200 or type(result.json) is not dict
                or type(result.json.get("id")) is not str or result.json["id"] != account["id"]):
            raise ValueError("authenticated identity differs from configured account")
        token = single_header(result.headers, "Token")
        authentication_id = str(uuid4())
        self.session_events.append({"user": user, "authentication_id": authentication_id})
        return ports.UserSession(principal_id=account["id"], authentication_id=authentication_id,
                                 credentials=token)


def resolve_request(action):
    return ports.RequestSpec(method=action.method, path="/api/v4/" + action.path.lstrip("/"),
        body=copy.deepcopy(action.body), query=wire_query(action.query or {}),
        headers=business_headers(action.headers or {}), files=copy.deepcopy(action.files))


class MattermostApiDriver(ports.ApiDriver):
    def __init__(self, client):
        self.client = client

    def send(self, spec, session):
        if spec.files is not None:
            raise ValueError("file requests are outside this pilot")
        result = self.client.exchange(spec.method, spec.path, body=spec.body,
                                      query=spec.query, headers=spec.headers, token=session,
                                      traceparent=spec.traceparent)
        return ports.RecordedResponse(status=result.status, headers=dict(result.headers),
            json=copy.deepcopy(result.json), text=result.text, trace_id=None,
            request=copy.deepcopy(spec), request_header_items=copy.deepcopy(result.request_header_items),
            header_items=copy.deepcopy(result.headers))


class MattermostNormalizer(ports.ResponseNormalizer):
    def normalize(self, response):
        if type(response.json) is not dict:
            raise ValueError("pilot response must be an actual JSON object")
        fields = copy.deepcopy(response.json)
        path = response.request.path
        if response.status == 200 and path.startswith("/api/v4/channels/") and path.endswith("/posts"):
            order, posts = fields.get("order"), fields.get("posts")
            if type(order) is not list or type(posts) is not dict:
                raise ValueError("PostList requires actual order and posts containers")
            if any(type(key) is not str or not key for key in order) or len(set(order)) != len(order):
                raise ValueError("PostList order identities are malformed")
            if any(type(key) is not str or not key or type(post) is not dict
                   or type(post.get("id")) is not str or post["id"] != key for key, post in posts.items()):
                raise ValueError("PostList map identities are malformed")
            if any(key not in posts for key in order):
                raise ValueError("PostList order references absent evidence")
        return ports.NormalizedResponse(succeeded=200 <= response.status < 300,
                                        fields=fields, status=response.status, raw=response)


def build_adapters(base_url, accounts, *, timeout=15.0):
    client = MattermostHttp(base_url, timeout=timeout)
    adapters = runner.Adapters(auth=MattermostAuthenticator(client, accounts),
        api=MattermostApiDriver(client), state=None, ui=None,
        recorder_factory=InMemoryRecorder, resolve_request=resolve_request,
        normalizer=MattermostNormalizer())
    return adapters, client
