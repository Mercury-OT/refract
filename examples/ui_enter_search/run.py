"""Run one approved search Scenario through two ordinary handler forms."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from refracto.runner import run_scenario
from examples.ui_enter_search.adapter import adapters
from examples.ui_enter_search.app import Application, application


ROOT = Path(__file__).resolve().parent
SCENARIO = ROOT / "scenario.yaml"
TARGET_FILES = ("app.py", "listener.js", "property.js")


def target_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in TARGET_FILES}


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
                       "key_press": asdict(step.key_press) if step.key_press else None}
                      for domain in report.domains for step in domain.steps],
            "browser_evidence": [{
                "step": evidence.step_id,
                "traffic": [{"method": traffic.request.method, "path": traffic.request.path,
                             "query": traffic.request.query} for traffic in evidence.traffic],
                "diagnostic_requests": [{"method": request.method, "path": request.path}
                                        for request in evidence.diagnostic_outgoing],
                "key_press": asdict(evidence.key_press) if evidence.key_press else None,
                "rendered_names": [item["fields"]["name"] for item in
                                   evidence.rendered["records.result_rows"]["anonymous"]],
                "user": evidence.user, "session_generation": evidence.session_generation,
            } for evidence in bound.ui.evidence],
            "browser_context_count": bound.ui.opened_contexts,
            "session_calls": bound.auth.session_calls,
            "api_send_calls": bound.api.send_calls,
            "server_requests": [{key: request[key] for key in ("method", "path", "query")}
                                for request in app.received],
            "server_responses": app.responses,
            "records": app.records,
            "target_faults": list(getattr(app, "faults_applied", [])),
            "closed_contexts": bound.ui.closed_contexts,
            "degradation": [item for domain in report.domains for item in domain.skipped]
                + [item for domain in report.domains for step in domain.steps for item in step.skipped],
        }
    verify_frozen_targets()
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", choices=("listener", "property", "both"), default="both")
    args = parser.parse_args()
    names = ("listener", "property") if args.implementation == "both" else (args.implementation,)
    rows = [run_case(name) for name in names]
    print(json.dumps({"consumer_version": 1, "runs": rows}, indent=2, sort_keys=True))
    return 0 if all(row["status"] == "PASSED" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
