"""Offline checks for the public pilot adapter; never contacts a product instance."""

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest

from examples.mattermost_api.adapters import (
    MattermostApiDriver, MattermostAuthenticator, MattermostHttp,
    MattermostNormalizer, build_adapters, resolve_request, safe_headers,
)
from examples.mattermost_api.plain_http import strict_equal
from refracto import ports, runner


def recording(body, *, status=200, path="/api/v4/posts/sample"):
    return ports.RecordedResponse(status=status, headers={}, json=body,
        text=json.dumps(body), trace_id=None,
        request=ports.RequestSpec(method="GET", path=path))


@contextmanager
def http_server(responses):
    observed = []
    queued = list(responses)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            observed.append({"method": self.command, "path": self.path,
                             "headers": dict(self.headers),
                             "body": json.loads(body) if body else None})
            status, headers, value = queued.pop(0)
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            for key, item in headers:
                self.send_header(key, item)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def accounts():
    return {user: {"id": user + "-id", "login_id": user,
                   "password": user + "-password-sentinel"} for user in ("owner", "peer")}


def test_normalizer_preserves_actual_types_missing_fields_and_owned_snapshots():
    body = {"id": "post-sample", "message": "observed", "meta": {
        "flag": False, "count": 0, "blank": "", "nullable": None, "values": [True, 1]}}
    original = deepcopy(body)
    response = recording(body)
    normalized = MattermostNormalizer().normalize(response)
    assert strict_equal(normalized.fields, original)
    assert normalized.fields is not body
    normalized.fields["meta"]["values"].append("later")
    assert strict_equal(body, original)
    missing = MattermostNormalizer().normalize(recording({"id": "other"}))
    assert missing.fields == {"id": "other"}
    assert "message" not in missing.fields


@pytest.mark.parametrize("status,body", [
    (200, {"id": "api.context.permissions.app_error"}),
    (401, {"id": "api.context.permissions.app_error"}),
    (400, {"id": "api.context.invalid_param.app_error"}),
    (403, {"id": "api.context.permissions.app_error"}),
    (403, {}),
])
def test_normalizer_does_not_invent_a_rejection_category_or_change_status(status, body):
    response = recording(body, status=status)
    normalized = MattermostNormalizer().normalize(response)
    assert normalized.fields == body
    assert normalized.status == status
    assert normalized.succeeded is (200 <= status < 300)
    assert normalized.raw is response


def test_postlist_retains_order_metadata_and_parents_outside_order():
    body = {"order": ["reply"], "posts": {
        "reply": {"id": "reply", "root_id": "parent", "message": "child"},
        "parent": {"id": "parent", "message": "root"}}, "next_post_id": "", "has_next": False}
    normalized = MattermostNormalizer().normalize(recording(body, path="/api/v4/channels/channel/posts"))
    assert strict_equal(normalized.fields, body)
    assert normalized.fields["posts"]["parent"]["message"] == "root"


@pytest.mark.parametrize("body", [
    {}, {"order": [], "posts": None}, {"order": None, "posts": {}},
    {"order": ["missing"], "posts": {}},
    {"order": ["a", "a"], "posts": {"a": {"id": "a"}}},
    {"order": [False], "posts": {}},
    {"order": ["a"], "posts": {"a": {"id": "b"}}},
    {"order": [], "posts": {"a": None}},
])
def test_postlist_malformed_observations_are_not_filled_or_filtered(body):
    before = deepcopy(body)
    with pytest.raises(ValueError):
        MattermostNormalizer().normalize(recording(body, path="/api/v4/channels/channel/posts"))
    assert strict_equal(body, before)


def test_empty_actual_postlist_is_valid_and_non_object_response_is_not():
    actual = {"order": [], "posts": {}}
    assert MattermostNormalizer().normalize(recording(
        actual, path="/api/v4/channels/channel/posts")).fields == actual
    for value in (None, [], "body", False):
        with pytest.raises(ValueError):
            MattermostNormalizer().normalize(recording(value))


def test_resolver_preserves_values_and_copies_mutable_inputs():
    action = ports.RequestAction(method="POST", path="posts", body={"nested": {"flag": False}},
                                 query={"page": 0}, headers={"X-Review": "sample"})
    spec = resolve_request(action)
    assert spec.path == "/api/v4/posts"
    assert spec.method == "POST"
    assert spec.query == {"page": "0"}
    assert spec.body == action.body
    spec.body["nested"]["flag"] = True
    assert action.body == {"nested": {"flag": False}}


@pytest.mark.parametrize("origin", ["https://example.com/", "http://example.com/",
    "http://127.0.0.1/api/v4", "http://owner:secret@127.0.0.1", "http://127.0.0.1?x=1"])
def test_transport_refuses_non_loopback_or_ambiguous_origins(origin):
    with pytest.raises(ValueError):
        MattermostHttp(origin)


def test_transport_retains_redirect_response_without_following_or_leaking_credentials():
    with http_server([(302, [("Location", "http://127.0.0.1:1/elsewhere")], {})]) as (base, observed):
        client = MattermostHttp(base)
        response = client.exchange("GET", "/api/v4/users/me", token="credential-sentinel")
        assert response.status == 302
        assert len(observed) == 1
        assert observed[0]["headers"]["Authorization"] == "Bearer credential-sentinel"
        assert "credential-sentinel" not in json.dumps(client.events)
        assert client.events[0]["status"] == 302


def test_actual_transport_query_body_and_header_observations_remain_available():
    with http_server([(201, [("X-Sample", "observed")], {"id": "post-sample", "message": "actual"})]) as (base, observed):
        client = MattermostHttp(base)
        driver = MattermostApiDriver(client)
        spec = ports.RequestSpec(method="POST", path="/api/v4/posts", body={"message": "actual"},
                                 query={"page": "0", "filter": "a b"})
        response = driver.send(spec, "session-sentinel")
        assert observed[0]["path"] == "/api/v4/posts?page=0&filter=a+b"
        assert observed[0]["body"] == {"message": "actual"}
        assert response.json == {"id": "post-sample", "message": "actual"}
        assert response.status == 201
        assert response.request == spec and response.request is not spec
        assert ("X-Sample", "observed") in response.header_items


def test_authentication_preserves_distinct_identity_and_hides_sensitive_exchange():
    responses = [(200, [("Token", user + "-token-sentinel")], {"id": user + "-id"})
                 for user in ("owner", "peer")]
    with http_server(responses) as (base, observed):
        client = MattermostHttp(base)
        auth = MattermostAuthenticator(client, accounts())
        owner, peer = auth.session("owner"), auth.session("peer")
        assert owner.principal_id != peer.principal_id
        assert owner.authentication_id != peer.authentication_id
        assert len(observed) == 2
        exported = json.dumps(client.events) + repr(owner) + repr(peer)
        for secret in ("owner-password-sentinel", "peer-password-sentinel",
                       "owner-token-sentinel", "peer-token-sentinel"):
            assert secret not in exported
        assert client.authentication_count == 2


def test_authentication_rejects_aliasing_and_login_returning_a_different_principal():
    duplicate = accounts()
    duplicate["peer"]["id"] = duplicate["owner"]["id"]
    with pytest.raises(ValueError):
        MattermostAuthenticator(MattermostHttp("http://127.0.0.1/"), duplicate)
    with http_server([(200, [("Token", "token")], {"id": "different"})]) as (base, _):
        with pytest.raises(ValueError):
            MattermostAuthenticator(MattermostHttp(base), accounts()).session("owner")


def test_authentication_failure_is_not_retried_or_treated_as_anonymous():
    with http_server([(401, [], {"id": "login.failed"})]) as (base, observed):
        auth = MattermostAuthenticator(MattermostHttp(base), accounts())
        with pytest.raises(ValueError):
            auth.session("owner")
        assert len(observed) == 1


def test_runner_keeps_the_same_session_after_an_actual_401(tmp_path):
    path = tmp_path / "case.yaml"
    path.write_text("""schema_version: 1
scenario: sample.session
users: [owner]
steps:
  - id: first
    do: {request: {method: GET, path: [users, me]}}
    expect: {response: [{check: status_equals, value: 200}]}
  - id: second
    do: {request: {method: GET, path: [users, me]}}
    expect: {response: [{check: status_equals, value: 200}]}
""")
    responses = [(200, [("Token", "same-token")], {"id": "owner-id"}),
                 (401, [], {"id": "login.expired"}), (200, [], {"id": "owner-id"})]
    with http_server(responses) as (base, observed):
        adapters, client = build_adapters(base, accounts())
        report = runner.run_scenario(path, adapters, projections=("backend", "contract"))
        assert report.status == "FAILED" and report.passed is False
        assert client.authentication_count == 1
        assert len(observed) == 3
        assert [row["headers"].get("Authorization") for row in observed[1:]] == ["Bearer same-token"] * 2


@pytest.mark.parametrize("left,right", [(False, 0), (True, 1), ({"a": False}, {"a": 0}),
                                        ([1, 2], [2, 1]), ({"a": 1}, {"a": 1, "b": 2})])
def test_plain_comparator_keeps_the_same_strict_business_equality(left, right):
    assert not strict_equal(left, right)


def test_secret_header_export_omits_values_but_preserves_nonsecret_duplicates():
    assert safe_headers([("Token", "secret"), ("Authorization", "secret"),
                         ("Set-Cookie", "secret"), ("X-Observed", "a"),
                         ("X-Observed", "b")]) == [["X-Observed", "a"], ["X-Observed", "b"]]


def test_export_refuses_a_known_credential_reflected_in_a_business_body():
    with http_server([(200, [], {"message": "reflected-token-sentinel"})]) as (base, _):
        client = MattermostHttp(base)
        client.exchange("GET", "/api/v4/users/me", token="reflected-token-sentinel")
        with pytest.raises(ValueError):
            client.assert_export_safe(client.events)


def test_input_inventory_rejects_missing_or_changed_frozen_approval(tmp_path):
    from examples.mattermost_api.run import APPROVED_INPUTS, verify_inputs
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({"scenarios": []}))
    with pytest.raises(ValueError, match="seven-file"):
        verify_inputs(tmp_path, approval)
    rows = [{"path": path, "sha256": digest} for path, digest in APPROVED_INPUTS.items()]
    rows[0]["sha256"] = "0" * 64
    approval.write_text(json.dumps({"scenarios": rows}))
    with pytest.raises(ValueError, match="reviewed panel"):
        verify_inputs(tmp_path, approval)


def test_offline_fault_changes_a_copy_and_requires_a_reached_target():
    from examples.mattermost_api.controls import inject
    first = recording({"id": "sample", "message": "before"})
    first.step_id = "create_post"
    later = recording({"id": "sample", "message": "after"})
    later.step_id = "read_after_edit"
    originals = [first, later]
    copied, change = inject("stale_edit", originals, "read_after_edit")
    assert later.json["message"] == "after"
    assert copied[1].json["message"] == "before"
    assert change["step"] == "read_after_edit"
    with pytest.raises(ValueError, match="not reached"):
        inject("stale_edit", originals, "absent")


def test_offline_fault_refuses_a_no_change_mutation():
    from examples.mattermost_api.controls import inject
    response = recording({"id": "permission"}, status=401)
    response.step_id = "nonmember_posts"
    with pytest.raises(ValueError, match="did not change"):
        inject("login_error_not_permission", [response], "nonmember_posts")


def test_plain_comparator_source_change_keeps_error_evidence_and_fails_teardown(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import time
    from examples.mattermost_api import plain_http
    case = plain_http.PlainCase.__new__(plain_http.PlainCase)
    case.config = {"frozen_sources": {"adapter": "before"}, "version": "11.7.15",
                   "observed_server_version": "11.7.15", "server_preflight": []}
    case.case_id, case.repetition, case.run_id = "S2", 1, "sample"
    case.started, case.started_utc, case.failed = time.perf_counter(), "sample", False
    case.checks, case.sessions, case.output = [], [], tmp_path
    case.http = SimpleNamespace(events=[], assert_export_safe=lambda value: None)
    monkeypatch.setattr(plain_http, "source_hashes", lambda: {"adapter": "after"})
    with pytest.raises(RuntimeError, match="source changed"):
        case.finish()
    artifact = json.loads((tmp_path / "result.json").read_text())
    assert artifact["status"] == "ERROR"
    assert artifact["execution_error_type"] == "SourceChanged"
    assert (tmp_path / "result.sha256").is_file()
