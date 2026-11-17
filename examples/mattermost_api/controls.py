"""Finite offline assertion controls on copies of actual pilot recordings.

No request is sent. These are artificial response changes, not product defects,
new product executions, or a simulation of their downstream system effects.
"""

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from refracto.declaration.binding import resolve_bindings
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import Input, RunUnique
from refracto.declaration.run_values import bind_run_values
from refracto.ports import RecordedResponse, RequestSpec
from refracto.projection.backend import _eval_response
from refracto.projection import contract

from .adapters import MattermostNormalizer
from .run import APPROVED_INPUTS, verify_inputs, write_json


PANEL = (
    ("stale_edit", "s03_post_edit_read.yaml", "read_after_edit"),
    ("login_error_not_permission", "s04_nonmember_post_rejected.yaml", "nonmember_posts"),
    ("validation_error_not_permission", "s04_nonmember_post_rejected.yaml", "nonmember_posts"),
    ("access_after_removal", "s05_membership_session_permissions.yaml", "peer_after_removal"),
    ("deleted_post_still_readable", "s06_post_delete_readback.yaml", "read_after_delete"),
)


def restore_declaration(path, artifact):
    declaration = load_scenario(path)
    if artifact.get("input_sha256") != APPROVED_INPUTS.get(path.name):
        raise ValueError("recording does not identify the approved Scenario")
    report = artifact.get("report", {})
    if (artifact.get("version") not in {"11.7.15", "11.11.4"}
            or artifact.get("status") != "PASSED" or report.get("status") != "PASSED"
            or report.get("scenario_id") != declaration.id):
        raise ValueError("control source must be a passing identified pilot execution")
    sources = report.get("run_unique_values", {}).get("backend", {})
    required = {item.kind for item in declaration.inputs if isinstance(item.value, RunUnique)}
    if set(sources) != required or any(type(value) is not str or not re.fullmatch(r"[0-9a-f]{32}", value)
                                      for value in sources.values()):
        raise ValueError("actual run unique sources are unavailable or malformed")
    # Restore observed source values in an execution copy; never rewrite YAML,
    # generate replacement identifiers, or pretend this is a live replay API.
    declaration.inputs = [Input(item.kind, sources[item.kind] if item.kind in required else item.value)
                          for item in declaration.inputs]
    bound, _ = bind_run_values(declaration, run_time=report.get("run_time"))
    return bound


def restore_recordings(artifact, declaration):
    domains = [item for item in artifact["report"].get("domains", []) if item.get("projection") == "backend"]
    if len(domains) != 1 or domains[0].get("status") != "PASSED":
        raise ValueError("one passing backend source domain is required")
    observations = domains[0].get("provider_recordings", [])
    expected_ids = [step.id for step in declaration.steps]
    if [row.get("step_id") for row in observations] != expected_ids:
        raise ValueError("recorded steps must exactly match the executed declaration")
    result = []
    for row in observations:
        spec = row["request"]
        if not row.get("is_final") or row.get("attempt_index") != 0:
            raise ValueError("control panel requires final one-shot observations")
        item = RecordedResponse(
            status=row["status"], headers=dict(row["headers"]), json=deepcopy(row["json"]),
            text=row["text"], trace_id=row["trace_id"],
            request=RequestSpec(method=spec["method"], path=spec["path"], body=deepcopy(spec["body"]),
                                query=deepcopy(spec["query"]), headers=dict(spec["headers"]),
                                traceparent=spec["traceparent"]),
            header_items=[tuple(pair) for pair in row["headers"]],
            request_header_items=[tuple(pair) for pair in row["request_header_items"]],
            **{key: row[key] for key in ("step_id", "attempt_index", "is_final", "template_path",
               "bound_logical_path", "actual_path", "request_id", "user", "session_generation")})
        result.append(item)
    return result


def evaluate(declaration, recordings):
    """Evaluate existing response checks; do not represent this as action replay."""
    normalizer = MattermostNormalizer()
    prior, checks = {}, []
    for step, record in zip(declaration.steps, recordings):
        bound = resolve_bindings(step, prior, inputs=declaration.inputs)
        actual = normalizer.normalize(record)
        for assertion in step.expect.response:
            result = _eval_response(assertion, actual, bound_values=bound,
                                    inputs=declaration.inputs, observed_status=record.status,
                                    observed_headers=record.header_items)
            checks.append({"step": step.id, "check": assertion.check,
                           "field": assertion.params.get("field"), "ok": result.ok})
        prior[step.id] = actual
    if not checks:
        raise ValueError("no response assertions were reached")
    contract_result = contract.run(declaration, deepcopy(recordings), MattermostNormalizer())
    return {"response_assertions_passed": all(row["ok"] for row in checks),
            "checks": checks, "contract_status": contract_result.status,
            "contract_steps": [asdict(step) for step in contract_result.steps]}


def inject(control, recordings, target):
    copied = deepcopy(recordings)
    by_step = {row.step_id: row for row in copied}
    if target not in by_step:
        raise ValueError("injection target was not reached")
    item = by_step[target]
    before = deepcopy(item)
    if control == "stale_edit":
        item.json["message"] = by_step["create_post"].json["message"]
    elif control == "login_error_not_permission":
        item.status = 401
    elif control == "validation_error_not_permission":
        item.status = 400
        item.json["id"] = "synthetic.validation.error"
    elif control == "access_after_removal":
        item.status, item.json = 200, deepcopy(by_step["peer_after_join"].json)
    elif control == "deleted_post_still_readable":
        item.status, item.json = 200, deepcopy(by_step["read_before_delete"].json)
    else:
        raise ValueError("unknown fixed control")
    item.text = json.dumps(item.json, separators=(",", ":"))
    if item.status == before.status and item.json == before.json:
        raise ValueError("injection did not change the observed response")
    return copied, {"step": target, "original_status": before.status,
                    "mutated_status": item.status, "original_json": before.json,
                    "mutated_json": item.json}


def run_controls(suite_dir, scenarios_dir, approval, output_dir):
    suite_dir, scenarios_dir = Path(suite_dir), Path(scenarios_dir)
    verify_inputs(scenarios_dir, approval)
    summary = json.loads((suite_dir / "summary.json").read_text())
    if summary.get("version") not in {"11.7.15", "11.11.4"}:
        raise ValueError("control suite version is not frozen")
    source_rows = {}
    for row in summary["records"]:
        if row["status"] == "PASSED" and row["scenario_file"] not in source_rows:
            source_rows[row["scenario_file"]] = row
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, filename, target in PANEL:
        source = source_rows.get(filename)
        if source is None:
            raise ValueError("fixed control panel has no passing actual source for " + filename)
        source_path = suite_dir / source["artifact"]
        if source_path.resolve().is_relative_to(suite_dir.resolve()) is False:
            raise ValueError("source artifact escapes its suite")
        raw = source_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("source artifact hash differs from the actual run summary")
        artifact = json.loads(raw)
        if artifact["version"] != summary["version"]:
            raise ValueError("source artifact belongs to a different version")
        declaration = restore_declaration(scenarios_dir / filename, artifact)
        observations = restore_recordings(artifact, declaration)
        normal = evaluate(declaration, observations)
        if not normal["response_assertions_passed"] or normal["contract_status"] != "PASSED":
            raise ValueError("unmodified observed response control did not pass")
        mutated, change = inject(name, observations, target)
        outcome = evaluate(declaration, mutated)
        failures = [row for row in outcome["checks"] if not row["ok"]]
        detected = any(row["step"] == target for row in failures)
        result = {"control": name, "scenario_file": filename, "version": artifact["version"],
                  "source_artifact_sha256": source["sha256"], "source_run_id": artifact["run_id"],
                  "kind": "artificial_offline_response_control", "live_requests": 0,
                  "injection_reached": True, "normal": normal, "change": change,
                  "outcome": outcome, "detected": detected, "failed_checks": failures}
        write_json(output / (name + ".json"), result)
        results.append({key: result[key] for key in ("control", "scenario_file", "version",
                       "source_artifact_sha256", "injection_reached", "detected", "failed_checks")})
    report = {"kind": "artificial_offline_response_controls", "records": results,
              "four_fault_classes_five_variants": True, "live_requests": 0,
              "all_detected": all(row["detected"] for row in results),
              "limits": ["Only response-assertion sensitivity on copied observed data was tested.",
                         "No altered target was executed; downstream system effects were not simulated.",
                         "Contract reuses these observations; it is not independent evidence.",
                         "This finite panel is not a product-quality percentage."]}
    write_json(output / "summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("suite-dir", "scenarios-dir", "approval", "output-dir"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    report = run_controls(args.suite_dir, args.scenarios_dir, args.approval, args.output_dir)
    print(json.dumps({"controls": len(report["records"]), "all_detected": report["all_detected"]}))
    return 0 if report["all_detected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
