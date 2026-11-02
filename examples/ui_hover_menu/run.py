"""Execute the fixed hover consumer with live and explicitly mocked requests."""
import hashlib
import json
from pathlib import Path

from examples.ui_hover_menu.adapter import adapters
from examples.ui_hover_menu.app import application
from refracto.ports import MockResponse
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SCENARIO = ROOT / "scenario.yaml"
TARGET_FILES = tuple("examples/ui_hover_menu/" + name
                     for name in ("app.py", "menu.css", "menu.js"))


def verify_target_sources():
    inventory = json.loads((ROOT / "target-sources.json").read_text(encoding="utf-8"))
    expected = inventory["sources"]
    if inventory["manifest_version"] != 1 or set(expected) != set(TARGET_FILES):
        raise ValueError("invalid target source inventory")
    for name in TARGET_FILES:
        if hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest() != expected[name]:
            raise ValueError("target source differs from the frozen example")
    return expected


def mock_plan():
    return [MockResponse(fixture_id="archived-list", source="mock-response.json",
                         method="GET", path="records", query={"status": "archived"},
                         response=json.loads((ROOT / "mock-response.json").read_text()))]


def execute(app, projection):
    if projection not in {"frontend", "e2e"}:
        raise ValueError("this consumer selects frontend or e2e")
    verify_target_sources()
    bundle = adapters(app)
    try:
        report = run_scenario(SCENARIO, bundle, projections=(projection,),
                             mock_plan=mock_plan() if projection == "frontend" else None)
        return report, bundle
    finally:
        verify_target_sources()


def summarize(report, bundle, implementation, projection):
    # Do not serialize actual field values, raw traffic or exception messages.
    return {
        "implementation": implementation, "projection": projection, "status": report.status,
        "steps": [{"id": step.step_id, "status": step.status,
                   "checks": [{"point": check.point, "check": check.check, "ok": check.ok}
                              for check in step.checks],
                   "hover_observed": step.hover is not None}
                  for domain in report.domains for step in domain.steps],
        "session_acquisitions": bundle.auth.session_calls,
        "contexts_opened": bundle.ui.opened_contexts,
        "contexts_closed": bundle.ui.closed_contexts,
    }


def run(implementation, projection):
    with application(implementation) as app:
        report, bundle = execute(app, projection)
        return summarize(report, bundle, implementation, projection)


def main():
    passed = True
    for implementation in ("css", "javascript"):
        for projection in ("frontend", "e2e"):
            try:
                summary = run(implementation, projection)
            except Exception:
                summary = {"implementation": implementation, "projection": projection,
                           "execution_error": "consumer execution failed"}
            print(json.dumps(summary, sort_keys=True))
            passed = passed and summary.get("status") == "PASSED"
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
