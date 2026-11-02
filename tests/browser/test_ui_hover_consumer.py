"""Real CSS/JavaScript hover, mock isolation, and unchanged-target fault controls."""
import copy

import pytest

from examples.ui_hover_menu.app import Application, application
from examples.ui_hover_menu.run import ROOT, SCENARIO, execute


@pytest.fixture(autouse=True)
def frozen_sources_and_declaration():
    paths = [ROOT / name for name in ("app.py", "menu.js", "menu.css", "target-sources.json",
                                    "mock-response.json", SCENARIO.name)]
    before = {path: path.read_bytes() for path in paths}
    yield
    assert {path: path.read_bytes() for path in paths} == before


def api_requests(app):
    return [item for item in app.received if item["path"].startswith("/api/")]


def assert_closed(bundle):
    assert bundle.auth.session_calls == 1
    assert bundle.ui.opened_contexts == bundle.ui.closed_contexts == 1


@pytest.mark.parametrize("implementation", ["css", "javascript"])
@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_real_hover_reveals_menu_before_separate_click(implementation, projection):
    with application(implementation) as app:
        before = copy.deepcopy(app.records)
        report, bundle = execute(app, projection)
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        steps = report.domains[0].steps
        assert [step.status for step in steps] == ["PASSED"] * 3
        assert steps[1].hover.target_matches == 1
        assert steps[1].hover.pointer_on_target is True
        evidence = bundle.ui.evidence
        assert [item.step_id for item in evidence] == ["open_page", "reveal_menu", "browse_archived"]
        assert evidence[0].rendered["records.menu_items"]["anonymous"] == []
        assert evidence[1].rendered["records.menu_items"]["anonymous"] == [
            {"fields": {"text": "Archived records"}}]
        assert evidence[0].traffic == evidence[1].traffic == []
        assert len(evidence[2].traffic) == 1
        assert evidence[2].traffic[0].request.path == "records"
        assert evidence[2].traffic[0].request.query == {"status": "archived"}
        assert evidence[2].rendered["records.result_rows"]["anonymous"] == [
            {"fields": {"name": "Archived record"}}]
        assert {item.user for item in evidence} == {"reader"}
        assert len({item.context_id for item in evidence}) == 1
        if projection == "frontend":
            assert api_requests(app) == []
            assert len(evidence[2].mock_recordings) == 1
        else:
            assert api_requests(app) == [{"method": "GET", "path": "/api/records", "query": "status=archived"}]
            assert len(report.domains[0].provider_recordings) == 1
        assert app.records == before
        assert_closed(bundle)


def inject_page(monkeypatch, fragment):
    original = Application.page

    def changed(self):
        return original(self).replace(b"</html>", fragment + b"</html>")

    monkeypatch.setattr(Application, "page", changed)


@pytest.mark.parametrize("implementation", ["css", "javascript"])
def test_delivered_hover_without_reveal_fails_and_blocks_click(monkeypatch, implementation):
    inject_page(monkeypatch, b"<style>#menu-items { display: none !important; }</style>")
    with application(implementation) as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED"]
        assert report.domains[0].steps[1].hover.pointer_on_target is True
        assert api_requests(app) == []
        assert_closed(bundle)


def test_already_visible_menu_cannot_claim_hover_proved_reveal(monkeypatch):
    inject_page(monkeypatch, b"<style>#menu-items { display: block !important; }</style>")
    with application("css") as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["FAILED", "BLOCKED", "BLOCKED"]
        assert len(bundle.ui.evidence) == 1
        assert api_requests(app) == []
        assert_closed(bundle)


@pytest.mark.parametrize("selector", ["#menu", "#menu-items", "#results"])
def test_missing_display_region_is_error_not_an_empty_count(monkeypatch, selector):
    inject_page(monkeypatch, f"<script>document.querySelector('{selector}').remove()</script>".encode())
    with application("css") as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["ERROR", "BLOCKED", "BLOCKED"]
        assert report.domains[0].steps[0].checks == []
        assert api_requests(app) == []
        assert_closed(bundle)


def test_correct_api_with_wrong_display_is_still_failed(monkeypatch):
    inject_page(monkeypatch, b"""<script>
      const append = Node.prototype.appendChild;
      Node.prototype.appendChild = function(child) {
        if (this.id === 'results') child.textContent = 'Active record';
        return append.call(this, child);
      };
    </script>""")
    with application("javascript") as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        final = report.domains[0].steps[-1]
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "FAILED"]
        assert all(check.ok for check in final.checks if check.point == "response")
        assert [check.ok for check in final.checks if check.point == "frontend"] == [False, False]
        assert len(api_requests(app)) == 1
        assert_closed(bundle)


def test_success_status_cannot_hide_wrong_query_response(monkeypatch):
    def ignored_filter(self, query):
        return 200, {"success": True, "data": {"records": copy.deepcopy(self.records)}}

    monkeypatch.setattr(Application, "response", ignored_filter)
    with application("css") as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        final = report.domains[0].steps[-1]
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "FAILED"]
        assert any(check.check == "collection_length" and not check.ok for check in final.checks)
        assert [check.ok for check in final.checks if check.point == "frontend"] == [True, False]
        assert len(api_requests(app)) == 1
        assert_closed(bundle)
