"""Actual browser Flow execution and isolated faults in the synthetic target."""
import copy
import json
import shutil

import pytest
import yaml

from examples.browser_flow.adapter import BrowserFlowUi
from examples.browser_flow.run import FLOW, REPOSITORY, TARGET_FILES, execute
from examples.browser_multi_origin.app import Application, application


@pytest.fixture(autouse=True)
def unchanged_product_and_approved_declarations():
    paths = [REPOSITORY / name for name in TARGET_FILES]
    paths += list(FLOW.parent.glob("*.yaml")) + list(FLOW.parent.glob("*.json"))
    before = {path: path.read_bytes() for path in paths}
    yield
    assert {path: path.read_bytes() for path in paths} == before


def business_requests(app):
    return [item for item in app.received if item["channel"] == "api" and item["method"] != "OPTIONS"]


def checks(report, node, point):
    return [check for check in report.scenarios[node].domains[0].checks if check.point == point]


def assert_closed_once(bundle):
    assert bundle.auth.session_calls == ["creator"]
    assert len(bundle.ui.opened) == 1
    assert bundle.ui.closed == [bundle.ui.opened[0]["context_id"]]


@pytest.mark.parametrize("implementation", ["promise", "async"])
def test_browser_flow_drives_same_page_and_observes_three_real_operations(monkeypatch, implementation):
    final_pages = []
    original_close = BrowserFlowUi.close_stepwise

    def observe_then_close(self, context):
        final_pages.append({"context": context,
                            "display": json.loads(context.page.locator("#result").inner_text()),
                            "record_id": context.page.locator("#record_id").input_value()})
        return original_close(self, context)

    monkeypatch.setattr(BrowserFlowUi, "close_stepwise", observe_then_close)
    with application(implementation) as app:
        report, bundle = execute(app)
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        assert [node.status for node in report.scenarios] == ["PASSED"] * 3
        assert [domain.projection for domain in report.domains] == ["e2e"]
        identity = report.parameter_history["e2e"]["record_id"][-1].value
        code = report.parameter_history["e2e"]["record_code"][-1].value
        calls = business_requests(app)
        assert [(call["method"], call["path"]) for call in calls] == [
            ("POST", "/api/records"), ("PATCH", "/api/records/" + identity),
            ("GET", "/api/records/" + identity)]
        assert [call["body"] for call in calls] == [
            {"name": "Initial record", "code": code}, {"name": "Updated record"}, None]
        assert app.records[identity] == {"id": identity, "code": code, "name": "Updated record", "category": "guide"}
        assert len(app.records) == 4
        recordings = report.domains[0].provider_recordings
        assert [record.request.method for record in recordings] == ["POST", "PATCH", "GET"]
        assert recordings[-1].json["data"] == app.records[identity]
        assert len({record.request_id for record in recordings}) == 3
        assert [(item["action"], item["target"]) for item in bundle.ui.actions] == [
            ("open", "records.page"), ("fill", "name"), ("fill", "code"), ("click", "create"),
            ("fill", "record_id"), ("fill", "name"), ("click", "update"), ("click", "read")]
        assert len({item["action_id"] for item in bundle.ui.actions}) == 8
        assert {item["context_id"] for item in bundle.ui.actions} == {bundle.ui.opened[0]["context_id"]}
        assert {(item["user"], item["session_generation"]) for item in bundle.ui.actions} == {("creator", 1)}
        assert_closed_once(bundle)
        assert len(final_pages) == 1
        assert final_pages[0]["context"].page.is_closed()
        assert final_pages[0]["record_id"] == identity
        assert final_pages[0]["display"] == {"success": True, "data": app.records[identity]}
        assert report.scenarios[2].domains[0].flow_reads["record_id"].writer_node == "create"
        assert report.scenarios[2].domains[0].flow_reads["expected_name"].writer_node == "update"
        assert [check.check for check in checks(report, 0, "frontend")] == ["objects_matching_count"] * 2
        assert all(check.ok for domain in report.domains for check in domain.checks)
        assert sum(item["channel"] == "page" and item["path"] == "/" for item in app.received) == 1


def test_repeated_browser_flows_do_not_reuse_created_identity_code_or_context():
    with application("promise") as app:
        first, first_bundle = execute(app)
        second, second_bundle = execute(app)
        assert first.status == second.status == "PASSED"
        assert first.run_id != second.run_id
        for key in ("record_id", "record_code"):
            assert first.parameter_history["e2e"][key][-1].value != second.parameter_history["e2e"][key][-1].value
        assert len(business_requests(app)) == 6
        assert len(app.records) == 5
        assert_closed_once(first_bundle)
        assert_closed_once(second_bundle)
        assert first_bundle.ui.opened[0]["context_id"] != second_bundle.ui.opened[0]["context_id"]


def test_correct_http_with_wrong_display_is_rejected_by_actual_ui_check(monkeypatch):
    original_page = Application.page

    def wrong_display_page(self):
        # Isolated rendering fault: the application's real fetch/response is untouched.
        script = b"""<script>
          const result = document.getElementById('result');
          const nativeText = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
          Object.defineProperty(result, 'textContent', {
            get() { return nativeText.get.call(this); },
            set(text) {
              const observed = JSON.parse(text);
              observed.data.name = 'Incorrect displayed name';
              nativeText.set.call(this, JSON.stringify(observed));
            }
          });
        </script>"""
        return original_page(self).replace(b"</html>", script + b"</html>")

    monkeypatch.setattr(Application, "page", wrong_display_page)
    with application("promise") as app:
        report, bundle = execute(app)
        assert report.status == "FAILED"
        assert report.scenarios[0].status == "FAILED"
        assert all(check.ok for check in checks(report, 0, "response"))
        assert [check.ok for check in checks(report, 0, "frontend")] == [False, True]
        assert [call["method"] for call in business_requests(app)] == ["POST"]
        assert app.records["r4"]["name"] == "Initial record"
        assert report.domains[0].provider_recordings[0].json["data"]["name"] == "Initial record"
        assert all(step.status == "BLOCKED" for node in report.scenarios[1:] for step in node.domains[0].steps)
        assert_closed_once(bundle)


def test_correct_update_acknowledgement_cannot_hide_stale_persisted_value(monkeypatch):
    original_response = Application.response

    def lost_update(self, method, path, query, body, headers):
        before = copy.deepcopy(self.records)
        status, payload = original_response(self, method, path, query, body, headers)
        if method == "PATCH":
            acknowledgement = copy.deepcopy(payload)
            self.records = before  # The isolated target loses the write after acknowledging it.
            return status, acknowledgement
        return status, payload

    monkeypatch.setattr(Application, "response", lost_update)
    with application("promise") as app:
        report, bundle = execute(app)
        assert report.status == "FAILED"
        assert [node.status for node in report.scenarios] == ["PASSED", "PASSED", "FAILED"]
        assert all(check.ok for check in report.scenarios[1].domains[0].checks)
        assert any(check.check == "field_equals" and not check.ok for check in checks(report, 2, "response"))
        assert [(check.check, check.ok) for check in checks(report, 2, "frontend")] == [("object_field_equals", False)]
        assert [call["method"] for call in business_requests(app)] == ["POST", "PATCH", "GET"]
        recordings = report.domains[0].provider_recordings
        assert recordings[1].json["data"]["name"] == "Updated record"
        assert recordings[2].json["data"]["name"] == "Initial record"
        assert app.records["r4"]["name"] == "Initial record"
        assert report.parameter_history["e2e"]["expected_name"][-1].value == "Updated record"
        assert_closed_once(bundle)


def test_missing_creation_id_cannot_publish_or_drive_a_guessed_later_request(monkeypatch):
    original_response = Application.response

    def missing_id(self, method, path, query, body, headers):
        status, payload = original_response(self, method, path, query, body, headers)
        if method == "POST":
            payload = copy.deepcopy(payload)
            del payload["data"]["id"]
        return status, payload

    monkeypatch.setattr(Application, "response", missing_id)
    with application("promise") as app:
        report, bundle = execute(app)
        assert report.status == "FAILED"
        assert any(check.check == "has" and not check.ok for check in checks(report, 0, "response"))
        assert all(check.ok for check in checks(report, 0, "frontend"))
        assert report.scenarios[0].domains[0].steps[-1].status == "FAILED"
        assert not report.scenarios[0].domains[0].flow_writes["record_id"].available
        assert not report.parameter_history["e2e"]["record_id"][-1].provenance.available
        assert [call["method"] for call in business_requests(app)] == ["POST"]
        assert len(bundle.ui.actions) == 4
        assert all(step.status == "BLOCKED" for node in report.scenarios[1:] for step in node.domains[0].steps)
        assert_closed_once(bundle)


@pytest.mark.parametrize("policy", ["stop", "continue"])
def test_failed_update_invalidates_old_flow_value_under_both_policies(monkeypatch, tmp_path, policy):
    # Only the explicitly labeled continue control changes its copied Flow policy.
    path = FLOW
    if policy == "continue":
        root = tmp_path / "continue-control"
        shutil.copytree(FLOW.parent, root, ignore=shutil.ignore_patterns("__pycache__"))
        path = root / FLOW.name
        document = yaml.safe_load(path.read_text())
        document["on_failure"] = "continue"
        path.write_text(yaml.safe_dump(document, sort_keys=False))
    original_response = Application.response

    def refused_update(self, method, resource, query, body, headers):
        if method == "PATCH":
            return 409, {"success": False, "data": copy.deepcopy(self.records[resource.rsplit("/", 1)[-1]])}
        return original_response(self, method, resource, query, body, headers)

    monkeypatch.setattr(Application, "response", refused_update)
    with application("promise") as app:
        report, bundle = execute(app, flow_path=path)
        assert report.status == "FAILED"
        assert report.scenarios[0].status == "PASSED"
        assert report.scenarios[1].status == "FAILED"
        assert any(check.check == "status_equals" and not check.ok for check in checks(report, 1, "response"))
        assert not report.scenarios[1].domains[0].flow_writes["expected_name"].available
        assert all(step.status == "BLOCKED" for step in report.scenarios[2].domains[0].steps)
        history = report.parameter_history["e2e"]["expected_name"]
        assert history[0].value == "Initial record"
        assert history[-1].provenance.available is False
        assert [call["method"] for call in business_requests(app)] == ["POST", "PATCH"]
        assert len(bundle.ui.actions) == 7
        assert app.records["r4"]["name"] == "Initial record"
        assert_closed_once(bundle)


def test_ambiguous_actual_dom_is_observation_error_before_any_business_request(monkeypatch):
    original_page = Application.page

    def duplicate_display(self):
        return original_page(self).replace(b"</main>", b'<pre id="result"></pre></main>')

    monkeypatch.setattr(Application, "page", duplicate_display)
    with application("promise") as app:
        report, bundle = execute(app)
        assert report.status == "FAILED"
        assert report.scenarios[0].domains[0].steps[0].status == "ERROR"
        assert business_requests(app) == []
        assert all(step.status == "BLOCKED" for node in report.scenarios[1:] for step in node.domains[0].steps)
        assert_closed_once(bundle)


def test_hidden_nonempty_actual_dom_is_unavailable_not_an_empty_display(monkeypatch):
    original_page = Application.page

    def hidden_display(self):
        return original_page(self).replace(b"</html>", b"<style>#result { visibility: hidden; }</style></html>")

    monkeypatch.setattr(Application, "page", hidden_display)
    with application("promise") as app:
        report, bundle = execute(app)
        assert report.status == "FAILED"
        assert report.scenarios[0].domains[0].steps[-1].status == "ERROR"
        assert [call["method"] for call in business_requests(app)] == ["POST"]
        assert app.records["r4"]["name"] == "Initial record"
        # Unavailable rendering is an observation error, not a false empty count.
        assert checks(report, 0, "frontend") == []
        assert all(step.status == "BLOCKED" for node in report.scenarios[1:] for step in node.domains[0].steps)
        assert_closed_once(bundle)
