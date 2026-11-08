"""Framework interference and global page errors remain distinct from bad UI."""
import json

import pytest
import yaml

from refracto import ports
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_flow, run_scenario
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport
from tests.browser.test_multi_origin_transport import Peer
from tests.test_flow_runtime import flow_path, scenario as flow_scenario


SENTINEL = "unpublished-page-exception-value"


class Auth(ports.Authenticator):
    def __init__(self):
        self.calls = []

    def identify(self, user):
        return "synthetic:" + user

    def session(self, user):
        self.calls.append(user)
        return ports.UserSession(principal_id=self.identify(user),
                                 authentication_id="session-" + str(len(self.calls)),
                                 credentials={})


class NoResponse(ports.ResponseNormalizer):
    def normalize(self, response):
        raise AssertionError("page-only checks must not normalize an API response")


def no_request(action):
    raise AssertionError("page-only checks must not issue a direct API request")


class PageDriver(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, peer, native):
        self.peer = peer
        self.evidence, self.actions, self.opened, self.closed = [], [], [], []
        self.browser = BrowserSupport(peer.url, self.read, timeout_ms=5000,
            network_policy=BrowserNetworkPolicy(
                api_endpoints=(ApiEndpoint(peer.url, "/api", "api"),)) if native else None)

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def supports_hover(self, mode):
        return mode in {"live", "mock"}

    def supports_key_press(self, mode, key):
        return mode in {"live", "mock"} and key == "Escape"

    def open_stepwise(self, session, **options):
        context = self.browser.open(context_options=session, **options)
        self.opened.append(context)
        return context

    def perform_step(self, context, permit, *, business_header_names=()):
        self.actions.append((permit.step_id, permit.action, permit.context_id))
        self.browser.validate_request_header_names(context, business_header_names)
        mapping = ({"url": self.peer.url + "/"} if permit.action == "open" else
                   {"selector": {"menu": "#menu", "entry": "#entry",
                                 "button": "#button"}[permit.target]})
        result = self.browser.perform(context, permit, **mapping)
        self.evidence.append(result.evidence)
        return result

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        self.closed.append(context)
        self.browser.close(context)

    @staticmethod
    def read(page):
        # Await the page's own acquisition outcome, not the expected greeting.
        page.wait_for_function("window.ready === true", timeout=5000)
        return {"page": {"identified": [], "anonymous": [{"fields": {
            "text": page.locator("#hello").text_content(),
            "menu_visible": page.locator("#panel").is_visible(),
            "suggestions_visible": page.locator("#suggestions").is_visible(),
            "value": page.locator("#entry").input_value(),
        }}]}}


def page(script):
    return ("""<!doctype html><style>
      #menu {position:absolute;left:80px;top:80px;width:150px;height:40px;}
      #panel {display:none;} #menu:hover #panel {display:block;}
    </style><div id="menu">Menu<div id="panel">Details</div></div>
    <input id="entry"><div id="suggestions" hidden>Suggestion</div>
    <button id="button">Continue</button><div id="hello">hello</div>
    <script>
      const entry=document.querySelector('#entry');
      const suggestions=document.querySelector('#suggestions');
      entry.oninput=()=>{suggestions.hidden=false;};
      entry.onkeydown=event=>{if(event.key==='Escape') suggestions.hidden=true;};
      window.ready=false;
    """ + script + "</script>").encode()


BOOTSTRAP = """
    document.querySelector('#hello').textContent='loading';
    fetch('/api/me',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
      .then(response=>response.json())
      .then(response=>{document.querySelector('#hello').textContent=
          response.data.reply === 'observed' ? 'hello' : 'wrong';})
      .catch(()=>{document.querySelector('#hello').textContent='unavailable';})
      .finally(()=>{window.ready=true;});
"""


@pytest.fixture
def application():
    peer = Peer()
    try:
        yield peer
    finally:
        peer.close()


def expect(field="text", value="hello"):
    return {"ui": [{"check": "objects_matching_count", "anchor": "page",
                    "field": field, "value": value, "count": 1}]}


def open_step(name):
    return {"id": name, "do": "open", "target": "page", "expect": expect()}


def after_step():
    return {"id": "after", "do": "click", "target": "button", "expect": expect()}


def page_only_steps(kind):
    if kind == "hover":
        return [{"id": "hover", "do": "hover", "target": "menu",
                 "expect": expect("menu_visible", True)}]
    if kind == "Escape":
        return [
            {"id": "fill", "do": "fill", "target": "entry", "value": "report",
             "expect": expect("suggestions_visible", True)},
            {"id": "escape", "do": "press", "target": "entry", "key": "Escape",
             "expect": expect("suggestions_visible", False)},
        ]
    return []


def fixtures():
    return [ports.MockResponse(fixture_id="bootstrap-" + str(index),
        source="synthetic bootstrap response", method="POST", path="api/me",
        response={"success": True, "data": {"reply": "observed"}}, status=200)
        for index in range(2)]


def adapters(peer, native):
    driver = PageDriver(peer, native)
    return Adapters(Auth(), None, None, driver, InMemoryRecorder, no_request, NoResponse())


def assert_closed(bundle):
    assert len(bundle.ui.opened) == 1
    assert bundle.ui.closed == bundle.ui.opened
    assert bundle.ui.opened[0].closed
    assert not bundle.ui.opened[0].browser.is_connected()
    assert len(bundle.auth.calls) == 1


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("kind", ["hover", "Escape", "none"])
@pytest.mark.parametrize("projection", ["e2e", "frontend"])
def test_mock_intervention_is_error_not_product_failure(
        tmp_path, application, native, kind, projection):
    application.page = page(BOOTSTRAP)
    steps = [open_step("first"), *page_only_steps(kind), open_step("second"), after_step()]
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "scenario": "records.reload",
                                  "users": ["reader"], "steps": steps}))
    bundle = adapters(application, native)
    report = run_scenario(path, bundle, projections=(projection,),
                         mock_plan=fixtures() if projection == "frontend" else None)
    domain = report.domains[0]
    blocked = projection == "frontend" and kind != "none"
    assert [step.status for step in domain.steps[:-2]] == ["PASSED"] * (len(steps) - 2)
    if blocked:
        assert [step.status for step in domain.steps[-2:]] == ["ERROR", "BLOCKED"]
        assert "mock_background_blocked" in domain.steps[-2].detail
        assert domain.steps[-2].checks == []
        assert report.status == "FAILED" and report.passed is False
        assert len(bundle.ui.actions) == len(steps) - 1
    else:
        assert [step.status for step in domain.steps[-2:]] == ["PASSED", "PASSED"]
        assert report.status == "PASSED" and report.passed is True
    if projection == "frontend":
        assert not any(item["path"].startswith("/api/") for item in application.requests)
        assert bundle.ui.opened[0].mock_queue.index == (1 if blocked else 2)
        assert [item["fixture_id"] for item in domain.mock_consumption] == (
            ["bootstrap-0"] if blocked else ["bootstrap-0", "bootstrap-1"])
    else:
        assert sum(item["path"] == "/api/me" for item in application.requests) == 2
    assert_closed(bundle)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("kind", ["hover", "Escape"])
def test_mock_intervention_remains_error_across_flow_nodes(
        tmp_path, application, native, kind):
    application.page = page(BOOTSTRAP)
    path = flow_path(tmp_path, [
        flow_scenario("prepare", [open_step("first"), *page_only_steps(kind)]),
        flow_scenario("reload", [open_step("second"), after_step()]),
        flow_scenario("later", [open_step("third")]),
    ])
    bundle = adapters(application, native)
    report = run_flow(path, bundle, projections=("frontend",), mock_plan=fixtures())
    assert [node.status for node in report.scenarios] == ["PASSED", "FAILED", "DEGRADED"]
    second = report.scenarios[1].domains[0]
    assert [step.status for step in second.steps] == ["ERROR", "BLOCKED"]
    assert "mock_background_blocked" in second.steps[0].detail
    assert report.scenarios[2].domains[0].steps[0].status == "BLOCKED"
    assert report.status == "FAILED" and report.passed is False
    assert {context_id for _, _, context_id in bundle.ui.actions} == {
        bundle.ui.opened[0].context_id}
    assert bundle.ui.opened[0].mock_queue.index == 1
    assert not any(item["path"].startswith("/api/") for item in application.requests)
    assert_closed(bundle)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("fault", ["timer_throw", "unhandled_promise", "console_error", "none"])
def test_global_page_error_reports_safe_reason_without_claiming_action_ownership(
        tmp_path, application, native, fault):
    statement = {
        "timer_throw": "throw new Error(" + json.dumps(SENTINEL) + ");",
        "unhandled_promise": "Promise.reject(new Error(" + json.dumps(SENTINEL) + "));",
        "console_error": "console.error(" + json.dumps(SENTINEL) + ");",
        "none": "void 0;",
    }[fault]
    application.page = page("setTimeout(()=>{window.ready=true;" + statement + "},0);")
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "scenario": "records.page_health",
        "users": ["reader"], "steps": [open_step("open"), after_step()]}))
    bundle = adapters(application, native)
    report = run_scenario(path, bundle, projections=("e2e",))
    if fault in {"timer_throw", "unhandled_promise"}:
        assert [step.status for step in report.domains[0].steps] == ["ERROR", "BLOCKED"]
        detail = report.domains[0].steps[0].detail
        assert "page_error" in detail
        assert "event handler failed" not in detail
        assert report.status == "FAILED" and report.passed is False
    else:
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED"]
        assert report.status == "PASSED" and report.passed is True
    assert SENTINEL not in repr(report)
    assert SENTINEL not in repr(report.domains[0])
    assert SENTINEL not in repr(report.localize())
    assert_closed(bundle)


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("fault,reason", [
    ("pending_action", "collection_timeout"),
    ("foreign_request", "policy_denied"),
    ("duplicate_target", "target_unavailable"),
    ("invalid_snapshot", "evidence_invalid"),
    ("cleanup", "cleanup_failed"),
    ("snapshot_and_cleanup", "evidence_invalid"),
])
def test_actual_browser_failure_category_reaches_final_report(
        tmp_path, application, monkeypatch, native, fault, reason):
    # These controls fail the actual primitive/observation/cleanup path. They do
    # not manufacture an ActionFailure or bypass the browser/helper boundary.
    foreign = Peer() if fault == "foreign_request" else None
    statements = "window.ready=true;"
    if fault == "pending_action":
        statements += """
          document.querySelector('#button').onclick=()=>{
            console.log('pending-action-started');
            return new Promise(()=>{});
          };
        """
    elif fault == "foreign_request":
        statements += "document.querySelector('#button').onclick=()=>fetch(" + json.dumps(
            foreign.url + "/api/not-allowed?value=" + SENTINEL) + ").catch(()=>{});"
    elif fault == "duplicate_target":
        statements += "document.body.append(document.querySelector('#button').cloneNode(true));"
    application.page = page(statements)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "scenario": "records.failure_reason",
        "users": ["reader"], "steps": [open_step("open"), after_step(), open_step("later")]}))
    bundle = adapters(application, native)
    cleanup_calls, delivered = [], []

    original_open = bundle.ui.open_stepwise

    def open_with_controls(*args, **kwargs):
        context = original_open(*args, **kwargs)
        context.page.on("console", lambda message: delivered.append(message.text))
        if fault in {"cleanup", "snapshot_and_cleanup"}:
            actual_close = context.browser_context.close

            def close_then_fail(*args, **kwargs):
                cleanup_calls.append(context)
                actual_close(*args, **kwargs)
                raise RuntimeError(SENTINEL)

            monkeypatch.setattr(context.browser_context, "close", close_then_fail)
        return context

    monkeypatch.setattr(bundle.ui, "open_stepwise", open_with_controls)
    if fault == "pending_action":
        actual_perform = bundle.ui.perform_step

        def bounded_after_startup(context, permit, **kwargs):
            result = actual_perform(context, permit, **kwargs)
            if permit.action == "open":
                # Keep browser startup's normal budget. The subsequent actual
                # never-resolving handler has a short, explicit test deadline.
                bundle.ui.browser._timeout_ms = 1000
            return result

        monkeypatch.setattr(bundle.ui, "perform_step", bounded_after_startup)
    if fault in {"invalid_snapshot", "snapshot_and_cleanup"}:
        actual_read = bundle.ui.browser._read_rendered
        calls = []

        def invalid_second_snapshot(page):
            calls.append(page)
            return actual_read(page) if len(calls) == 1 else []

        monkeypatch.setattr(bundle.ui.browser, "_read_rendered", invalid_second_snapshot)
    try:
        report = run_scenario(path, bundle, projections=("e2e",))
        steps = report.domains[0].steps
        assert report.status == "FAILED" and report.passed is False
        assert steps[0].status == "PASSED"
        if fault == "cleanup":
            assert [step.status for step in steps] == ["PASSED", "PASSED", "ERROR"]
            failed = steps[-1]
        else:
            assert [step.status for step in steps] == ["PASSED", "ERROR", "BLOCKED"]
            failed = steps[1]
        assert reason in failed.detail
        if fault == "snapshot_and_cleanup":
            assert "cleanup_failed" in failed.detail
        if fault == "pending_action":
            assert "pending-action-started" in delivered
        if foreign is not None:
            assert foreign.requests == []
        assert len(cleanup_calls) == (1 if fault in {"cleanup", "snapshot_and_cleanup"} else 0)
        assert SENTINEL not in repr(report)
        assert SENTINEL not in repr(report.domains[0])
        assert SENTINEL not in repr(report.localize())
        assert_closed(bundle)
    finally:
        if foreign is not None:
            foreign.close()
