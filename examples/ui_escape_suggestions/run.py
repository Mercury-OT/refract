"""Run the fixed page-only Escape obligation on two ordinary handler variants."""
import hashlib
import json
from pathlib import Path

from examples.ui_escape_suggestions.adapter import adapters
from examples.ui_escape_suggestions.app import application
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SCENARIO = ROOT / "scenario.yaml"
TARGET_FILES = tuple("examples/ui_escape_suggestions/" + name
                     for name in ("app.py", "search.css", "search.js"))


def verify_target_sources():
    inventory = json.loads((ROOT / "target-sources.json").read_text(encoding="utf-8"))
    expected = inventory["sources"]
    if inventory["manifest_version"] != 1 or set(expected) != set(TARGET_FILES):
        raise ValueError("invalid target source inventory")
    for name in TARGET_FILES:
        if hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest() != expected[name]:
            raise ValueError("target source differs from the frozen example")
    return expected


def execute(app, projection):
    if projection not in {"frontend", "e2e"}:
        raise ValueError("this consumer selects frontend or e2e")
    verify_target_sources()
    bundle = adapters(app)
    try:
        report = run_scenario(SCENARIO, bundle, projections=(projection,),
                             mock_plan=[] if projection == "frontend" else None)
        return report, bundle
    finally:
        verify_target_sources()


def summarize(report, bundle, implementation, projection):
    # Actual input, selectors, raw evidence and exception messages are not exported.
    return {"implementation": implementation, "projection": projection, "status": report.status,
            "steps": [{"id": step.step_id, "status": step.status,
                       "checks": [{"point": check.point, "check": check.check, "ok": check.ok}
                                  for check in step.checks],
                       "key_delivery_observed": step.key_press is not None}
                      for domain in report.domains for step in domain.steps],
            "session_acquisitions": bundle.auth.session_calls,
            "contexts_opened": bundle.ui.opened_contexts,
            "contexts_closed": bundle.ui.closed_contexts}


def run(implementation, projection):
    with application(implementation) as app:
        report, bundle = execute(app, projection)
        return summarize(report, bundle, implementation, projection)


def main():
    passed = True
    for implementation in ("listener", "property"):
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
