"""Real keyboard cancellation and fault controls on the unchanged neutral target."""
import pytest

from examples.ui_escape_suggestions.app import Application, application
from examples.ui_escape_suggestions.run import ROOT, SCENARIO, execute


@pytest.fixture(autouse=True)
def frozen_sources_and_declaration():
    paths = [ROOT / name for name in ("app.py", "search.js", "search.css",
                                    "target-sources.json", SCENARIO.name)]
    before = {path: path.read_bytes() for path in paths}
    yield
    assert {path: path.read_bytes() for path in paths} == before


def assert_closed(bundle):
    assert bundle.auth.session_calls == 1
    assert bundle.ui.opened_contexts == bundle.ui.closed_contexts == 1


def fields(evidence):
    return evidence.rendered["records.search_input"]["anonymous"][0]["fields"]


@pytest.mark.parametrize("implementation", ["listener", "property"])
@pytest.mark.parametrize("projection", ["frontend", "e2e"])
def test_real_escape_closes_suggestions_and_preserves_input(implementation, projection):
    with application(implementation) as app:
        report, bundle = execute(app, projection)
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        assert [step.status for step in report.domains[0].steps] == ["PASSED"] * 3
        receipt = report.domains[0].steps[-1].key_press
        assert receipt.key == "Escape"
        assert receipt.focused is True
        assert receipt.target_matches == receipt.keydown_count == receipt.keyup_count == 1
        evidence = bundle.ui.evidence
        assert [item.step_id for item in evidence] == [
            "open_search", "enter_search_text", "dismiss_suggestions"]
        assert [fields(item) for item in evidence] == [
            {"value": "", "suggestions_visible": False},
            {"value": "report", "suggestions_visible": True},
            {"value": "report", "suggestions_visible": False}]
        assert all(item.traffic == [] and item.mock_recordings == [] for item in evidence)
        assert len({item.context_id for item in evidence}) == 1
        assert {item.user for item in evidence} == {"reader"}
        assert not any(path.startswith("/api/") for path in app.received)
        assert report.domains[0].provider_recordings == []
        assert_closed(bundle)


def replace_script(monkeypatch, before, after):
    original = Application.script

    def changed(self):
        content = original(self)
        assert before in content
        return content.replace(before, after)

    monkeypatch.setattr(Application, "script", changed)


@pytest.mark.parametrize("implementation", ["listener", "property"])
@pytest.mark.parametrize("replacement,wrong_field", [
    (b"void 0;", "suggestions_visible"),
    (b"panel.hidden = true; input.value = '';", "value"),
])
def test_delivered_escape_does_not_hide_wrong_ui(monkeypatch, implementation, replacement, wrong_field):
    replace_script(monkeypatch, b"panel.hidden = true;", replacement)
    with application(implementation) as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "FAILED"]
        assert report.domains[0].steps[-1].key_press.key == "Escape"
        assert sum(not check.ok for check in report.domains[0].steps[-1].checks) == 1
        actual = fields(bundle.ui.evidence[-1])
        assert actual[wrong_field] == (True if wrong_field == "suggestions_visible" else "")
        assert_closed(bundle)


def test_never_opened_suggestions_cannot_vacuously_prove_dismissal(monkeypatch):
    replace_script(monkeypatch, b"panel.hidden = matches.length === 0;", b"panel.hidden = true;")
    with application() as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "FAILED", "BLOCKED"]
        assert len(bundle.ui.evidence) == 2
        assert report.domains[0].steps[-1].key_press is None
        assert_closed(bundle)


@pytest.mark.parametrize("fault", [
    b"panel.remove();",
    b"panel.after(panel.cloneNode(true));",
    b"document.body.append(panel.cloneNode(true));",
    b"input.setAttribute('aria-controls', 'unrelated');",
    b"input.after(input.cloneNode(true));",
    b"document.body.append(input.cloneNode(true));",
])
def test_missing_or_ambiguous_observation_is_error_not_false(monkeypatch, fault):
    replace_script(monkeypatch, b"panel.hidden = matches.length === 0;",
                   b"panel.hidden = matches.length === 0; " + fault)
    with application() as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "ERROR", "BLOCKED"]
        assert len(bundle.ui.evidence) == 1
        assert report.domains[0].steps[1].checks == []
        assert_closed(bundle)


def test_wrong_focus_is_not_repaired_before_escape(monkeypatch):
    replace_script(monkeypatch, b"panel.hidden = matches.length === 0;",
                   b"panel.hidden = matches.length === 0; document.getElementById('help').focus();")
    with application() as app:
        report, bundle = execute(app, "e2e")
        assert report.status == "FAILED"
        assert [step.status for step in report.domains[0].steps] == ["PASSED", "PASSED", "ERROR"]
        assert len(bundle.ui.evidence) == 2
        assert report.domains[0].steps[-1].key_press is None
        assert fields(bundle.ui.evidence[-1])["suggestions_visible"] is True
        assert_closed(bundle)
