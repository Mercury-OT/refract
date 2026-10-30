"""Execute every fixed consumer case, retaining passes and supported-scope gaps."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from refracto.runner import run_scenario
import refracto
import refracto_browser

from examples.browser_multi_origin.adapter import adapters
from examples.browser_multi_origin.app import application


ROOT = Path(__file__).resolve().parent
CASES = (
    "c01_static_ready", "c02_public_list", "c03_filter", "c04_next_page", "c05_create",
    "c06_read_created", "c07_update_read", "c08_delete_list", "c09_anonymous_refusal", "c10_named_access",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_case(case, implementation, *, maintenance=False, legacy=False):
    if case not in CASES:
        raise ValueError("case is not in the frozen panel")
    path = ROOT / "scenarios" / (case + ".yaml")
    started = time.perf_counter()
    with application(implementation, maintenance) as app:
        report = run_scenario(path, adapters(app, legacy=legacy), projections=("e2e",))
        row = {
            "case_id": case, "implementation": implementation,
            "maintenance": maintenance, "legacy_helper": legacy,
            "scenario_sha256": digest(path), "status": report.status,
            "steps": [{"id": step.step_id, "status": step.status, "detail": step.detail,
                       "checks": [{"point": check.point, "check": check.check, "ok": check.ok}
                                  for check in step.checks]}
                      for domain in report.domains for step in domain.steps],
            "server_requests": list(app.received),
            "service_origins": {"page": app.page_url, "api": app.api_url, "static": app.static_url},
            "recorded_requests": [
                {"method": recording.request.method, "logical_path": recording.request.path,
                 "status": recording.status, "actual_path": recording.actual_path,
                 "actual_origin": getattr(getattr(recording, "browser_identity", None), "origin", None)}
                for domain in report.domains for recording in domain.provider_recordings],
            "remaining_records": list(app.records.values()),
            "binding_configuration": {"selector_prefix": app.selector_prefix,
                                      "api_prefix": app.api_prefix},
        }
    row["elapsed_seconds"] = time.perf_counter() - started
    return row


def source_inventory():
    return {path.relative_to(ROOT).as_posix(): digest(path)
            for path in sorted(ROOT.rglob("*")) if path.is_file()
            and "__pycache__" not in path.parts and path.suffix in {".py", ".js", ".yaml"}}


def engine_inventory():
    sources = {}
    for module in (refracto, refracto_browser):
        root = Path(module.__file__).resolve().parent
        sources.update({module.__name__ + "/" + path.relative_to(root).as_posix(): digest(path)
                        for path in sorted(root.rglob("*.py"))})
    return sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", action="store_true", help="use the baseline helper without the new policy")
    parser.add_argument("--maintenance", action="store_true", help="use the fixed selector/API-prefix change")
    parser.add_argument("--expected-engine", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = args.expected_engine.resolve()
    for module in (refracto, refracto_browser):
        if not Path(module.__file__).resolve().is_relative_to(expected):
            raise SystemExit("engine import does not match the requested frozen source")
    input_sources, engine_sources = source_inventory(), engine_inventory()
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    rows = [run_case(case, implementation, maintenance=args.maintenance, legacy=args.legacy)
            for implementation in ("promise", "async") for case in CASES]
    counts = dict(Counter(row["status"] for row in rows))
    if input_sources != source_inventory() or engine_sources != engine_inventory():
        raise SystemExit("consumer or engine sources changed during the measurement")
    data = {"panel_version": 1, "label": args.label,
            "started_at_utc": started_at,
            "expected_units": len(CASES) * 2, "executed_units": len(rows),
            "status_counts": counts, "elapsed_seconds": time.perf_counter() - started,
            "human_effort": {"writing_minutes": None, "diagnosis_minutes": None,
                             "review_minutes": None, "reason": "not measured"},
            "source_sha256": input_sources, "engine_source_sha256": engine_sources,
            "records": rows}
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"label": args.label, "units": len(rows), "status_counts": counts,
                      "elapsed_seconds": data["elapsed_seconds"]}, sort_keys=True))
    # This is a measurement command, not a business acceptance gate. The JSON
    # retains non-passing results; normal consumer acceptance requires PASSED.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
