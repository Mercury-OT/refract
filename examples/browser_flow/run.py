"""Run the approved browser Flow against both unchanged synthetic frontends."""
import hashlib
import json
from pathlib import Path

from examples.browser_flow.adapter import build_adapters
from examples.browser_multi_origin.app import application
from refracto.runner import run_flow


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
FLOW = ROOT / "browser.flow.yaml"
TARGET_FILES = tuple("examples/browser_multi_origin/" + name
                     for name in ("app.py", "promise.js", "async.js"))


def verify_target_sources():
    """Check the fixed source set, including after an interrupted execution."""
    inventory = json.loads((ROOT / "target-sources.json").read_text(encoding="utf-8"))
    expected = inventory["sources"]
    if inventory["manifest_version"] != 1 or set(expected) != set(TARGET_FILES):
        raise ValueError("invalid target source inventory")
    for name in TARGET_FILES:
        actual = hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest()
        if actual != expected[name]:
            raise ValueError("target source differs from the frozen example")
    return expected


def execute(app, flow_path=FLOW):
    """Return the native report and in-memory adapter diagnostics."""
    verify_target_sources()
    bundle = build_adapters(app)
    try:
        report = run_flow(flow_path, bundle, projections=("e2e",))
        return report, bundle
    finally:
        verify_target_sources()


def summarize(report, bundle, implementation):
    """Publish statuses only; raw values and diagnostic details stay in memory."""
    return {
        "implementation": implementation,
        "flow_id": report.flow_id,
        "status": report.status,
        "scenarios": [{
            "node_id": node.node_id, "scenario_id": node.scenario_id,
            "status": node.status,
            "domains": [{
                "projection": domain.projection, "status": domain.status,
                "steps": [{"id": step.step_id, "status": step.status,
                           "checks": [{"point": check.point, "check": check.check,
                                       "ok": check.ok} for check in step.checks]}
                          for step in domain.steps],
            } for domain in node.domains],
        } for node in report.scenarios],
        "session_acquisitions": len(bundle.auth.session_calls),
        "contexts_opened": len(bundle.ui.opened),
        "contexts_closed": len(bundle.ui.closed),
        "actions": len(bundle.ui.actions),
    }


def run(implementation):
    with application(implementation) as app:
        report, bundle = execute(app)
        return summarize(report, bundle, implementation)


def main():
    passed = True
    for implementation in ("promise", "async"):
        try:
            summary = run(implementation)
        except Exception:
            # This is an execution error, not a reconstructed native Flow result.
            summary = {"implementation": implementation,
                       "execution_error": "consumer execution failed"}
        print(json.dumps(summary, sort_keys=True))
        passed = passed and summary.get("status") == "PASSED"
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
