"""Run the same six-step Scenario against either synthetic list editor."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from refracto.runner import run_scenario
from examples.ui_object_targets.adapter import adapters
from examples.ui_object_targets.app import Application, application


ROOT = Path(__file__).resolve().parent
SCENARIO = ROOT / "scenario.yaml"


def target_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("app.py", "table.js", "cards.js")}


def verify_frozen_targets():
    expected = json.loads((ROOT / "target-sources.json").read_text())["sha256"]
    if target_hashes() != expected:
        raise ValueError("synthetic target source differs from its frozen baseline")


def run_case(implementation, *, app_type=Application, timeout_ms=5000):
    verify_frozen_targets()
    with application(implementation, app_type=app_type) as app:
        bound = adapters(app, timeout_ms=timeout_ms)
        report = run_scenario(SCENARIO, bound, projections=("e2e",))
        row = {
            "implementation": implementation, "status": report.status,
            "scenario_sha256": hashlib.sha256(SCENARIO.read_bytes()).hexdigest(),
            "target_sha256": target_hashes(),
            "steps": [{"id": step.step_id, "status": step.status, "detail": step.detail,
                       "checks": [{"point": check.point, "check": check.check, "ok": check.ok}
                                  for check in step.checks],
                       "selection": asdict(step.object_selection) if step.object_selection else None}
                      for domain in report.domains for step in domain.steps],
            # Synthetic body values are useful evidence. Credentials are omitted.
            "server_requests": [{key: request[key] for key in ("method", "path", "body")}
                                for request in app.received],
            "records": list(app.records.values()),
            "target_faults": list(getattr(app, "faults_applied", [])),
            "closed_contexts": bound.ui.closed_contexts,
            "degradation": [item for domain in report.domains for item in domain.skipped]
                + [item for domain in report.domains for step in domain.steps for item in step.skipped],
        }
    verify_frozen_targets()
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", choices=("table", "cards", "both"), default="both")
    args = parser.parse_args()
    names = ("table", "cards") if args.implementation == "both" else (args.implementation,)
    rows = [run_case(name) for name in names]
    print(json.dumps({"consumer_version": 1, "runs": rows}, indent=2, sort_keys=True))
    return 0 if all(row["status"] == "PASSED" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
