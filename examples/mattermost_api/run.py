"""Run the externally approved six-case panel without rewriting its inputs."""

import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from datetime import datetime, timezone
from uuid import uuid4

from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario

from .adapters import MattermostHttp, build_adapters, safe_headers, single_header, strict_json


APPROVED_INPUTS = {
    "s01_channel_rename.yaml": "82121ceb36a0fa082980eff25a684d5df9194f7b75c62904e7faf56d4ae5a63a",
    "s02_post_create_read.yaml": "72da52675e9acc7527ee3e7c0e7c8d1bcb7ae3c0287ab60745791626820ced3b",
    "s03_post_edit_read.yaml": "b743138f9ae31e3d8469def500731f41f676f6247034c1fe29848c80329e702f",
    "s04_nonmember_post_rejected.yaml": "b1be358cc3ad6019e5ebddb0acd5bf691e43cefd930df7a6623575f8a7945e3a",
    "s05_membership_session_permissions.yaml": "87474b10658c67193186c692e9f13b53ab1e164ffe6d3b17ecd61a0e05cb9b68",
    "s06_post_delete_readback.yaml": "ae577ef432c9c75cbc3141ff5e3315856be02618ba2743e043c8b3e6876daa42",
    "shared/prepare_private_channel.yaml": "70fa12a879834049766ddb6869c7320e7c51c4ca6fa1e57a21f634adcdf9edca",
}
PIN_SHA256 = "07b7baeb7df66e2c89497c43feb09925a05b4348ede01f5b5425c3660475f3be"
CASES = tuple(name for name in APPROVED_INPUTS if not name.startswith("shared/"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def verify_inputs(directory, approval):
    directory = Path(directory).resolve()
    approved = strict_json(Path(approval).read_text(encoding="utf-8"))
    rows = approved.get("scenarios") if isinstance(approved, dict) else None
    if type(rows) is not list or len(rows) != len(APPROVED_INPUTS):
        raise ValueError("approval inventory is not the frozen seven-file panel")
    if any(type(row) is not dict or set(row) != {"path", "sha256"} for row in rows):
        raise ValueError("approval row is malformed")
    supplied = {row["path"]: row["sha256"] for row in rows}
    if supplied != APPROVED_INPUTS:
        raise ValueError("approval hashes differ from the reviewed panel")
    manifest = {}
    for name, digest in APPROVED_INPUTS.items():
        source = directory / name
        if source.is_symlink() or not source.is_file() or sha256(source) != digest:
            raise ValueError("reviewed Scenario bytes changed or are missing")
        manifest[name] = digest
    for name in CASES:
        pin = directory / name.replace(".yaml", ".includes.json")
        if pin.is_symlink() or not pin.is_file() or sha256(pin) != PIN_SHA256:
            raise ValueError("reviewed include pin bytes changed or are missing")
        manifest[pin.name] = PIN_SHA256
        load_scenario(directory / name)
    return manifest


def source_manifest():
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "refracto").rglob("*.py")) + list(Path(__file__).parent.glob("*.py"))
    return {str(path.relative_to(root)): sha256(path) for path in sorted(paths)}


def serialize_recording(record):
    request = record.request
    return {
        "status": record.status, "json": copy.deepcopy(record.json), "text": record.text,
        "headers": safe_headers(record.header_items or list(record.headers.items())),
        "trace_id": record.trace_id,
        "request": {"method": request.method, "path": request.path,
                    "body": copy.deepcopy(request.body), "query": copy.deepcopy(request.query),
                    "headers": safe_headers(list(request.headers.items())),
                    "traceparent": request.traceparent},
        "request_header_items": safe_headers(record.request_header_items or []),
        **{name: getattr(record, name) for name in (
            "step_id", "attempt_index", "is_final", "template_path", "bound_logical_path",
            "actual_path", "request_id", "user", "session_generation")},
    }


def serialize_report(report):
    return {
        "scenario_id": report.scenario_id, "status": report.status, "passed": report.passed,
        "selected": report.selected, "source_lookup": copy.deepcopy(report.source_lookup),
        "run_unique_values": copy.deepcopy(report.run_unique_values),
        "run_time": report.run_time, "run_time_source": report.run_time_source,
        "run_time_values": copy.deepcopy(report.run_time_values),
        "domains": [{
            "projection": domain.projection, "status": domain.status, "passed": domain.passed,
            "skipped": list(domain.skipped), "not_checked": list(domain.not_checked),
            "steps": [dataclasses.asdict(step) for step in domain.steps],
            "provider_recordings": [serialize_recording(record) for record in domain.provider_recordings],
        } for domain in report.domains],
        "export_omissions": ["credential and cookie headers", "authentication request/response bodies"],
        "evidence_note": "Contract reuses backend observations and normalization; it is not independent evidence.",
    }


def write_json(path, value):
    path = Path(path)
    # Exclusive creation preserves previous failed attempts and run artifacts.
    payload = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def run_panel(*, scenarios_dir, approval, accounts_file, base_url, output_dir,
              version, repetitions=3, timeout=15.0):
    if version not in {"11.7.15", "11.11.4"}:
        raise ValueError("version is not one of the two reviewed targets")
    if type(repetitions) is not int or not 1 <= repetitions <= 3:
        raise ValueError("repetitions must be between one and three")
    inputs = verify_inputs(scenarios_dir, approval)
    accounts = strict_json(Path(accounts_file).read_text(encoding="utf-8"))
    sources = source_manifest()
    root = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    suite_id = "api-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12]
    suite = Path(output_dir) / suite_id
    suite.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = utc_now()
    metadata = {"suite_id": suite_id, "version": version, "started_at": started,
                "refract_commit": head, "python": platform.python_version(),
                "inputs": inputs, "sources": sources, "projections": ["backend", "contract"],
                "repetitions": repetitions, "planned_runs": len(CASES) * repetitions}
    write_json(suite / "freeze.json", metadata)
    health = MattermostHttp(base_url, timeout=timeout)
    try:
        ping = health.exchange("GET", "/api/v4/system/ping")
        observed_version = single_header(ping.headers, "X-Version-Id")
        if ping.status != 200 or not (observed_version == version or observed_version.startswith(version + ".")):
            raise ValueError("actual server version differs from the frozen version")
        write_json(suite / "server.json", {"observed_version": observed_version, "ping": health.events})
    except Exception as exc:
        write_json(suite / "environment-error.json", {"status": "ERROR", "error_type": type(exc).__name__,
                   "message": "Server version or health preflight failed; no Scenario execution started.",
                   "events": health.events, "ended_at": utc_now()})
        return suite, False
    rows = []
    for repetition in range(1, repetitions + 1):
        for filename in CASES:
            run_id = f"{filename.removesuffix('.yaml')}-rep-{repetition:02}"
            target = suite / run_id
            target.mkdir(mode=0o700)
            adapters, client = build_adapters(base_url, accounts, timeout=timeout)
            begin = time.perf_counter()
            artifact = {"run_id": run_id, "version": version, "scenario_file": filename,
                        "repetition": repetition, "started_at": utc_now(), "input_sha256": inputs[filename]}
            try:
                if verify_inputs(scenarios_dir, approval) != inputs or source_manifest() != sources:
                    raise ValueError("frozen inputs or source changed during the experiment")
                report = run_scenario(Path(scenarios_dir) / filename, adapters,
                                      projections=("backend", "contract"))
                artifact.update(report=serialize_report(report), status=report.status)
            except Exception as exc:
                artifact.update(status="ERROR", error_type=type(exc).__name__,
                                error="Pilot runner failed outside a completed native report.")
            artifact.update(ended_at=utc_now(), duration_seconds=time.perf_counter() - begin,
                            http_events=copy.deepcopy(client.events), http_count=client.request_count,
                            authentication_count=client.authentication_count,
                            sessions=copy.deepcopy(adapters.auth.session_events))
            try:
                client.assert_export_safe(artifact)
                write_json(target / "result.json", artifact)
            except ValueError:
                artifact = {"run_id": run_id, "status": "ERROR", "error": "Evidence export refused known credential content.",
                            "ended_at": utc_now()}
                write_json(target / "export-error.json", artifact)
            artifact_file = target / ("result.json" if (target / "result.json").exists() else "export-error.json")
            rows.append({"run_id": run_id, "scenario_file": filename, "repetition": repetition,
                         "status": artifact["status"], "artifact": str(artifact_file.relative_to(suite)),
                         "sha256": sha256(artifact_file), "duration_seconds": artifact.get("duration_seconds"),
                         "http_count": artifact.get("http_count"), "authentication_count": artifact.get("authentication_count")})
            print(json.dumps({"run_id": run_id, "status": artifact["status"]}), flush=True)
    unchanged = verify_inputs(scenarios_dir, approval) == inputs and source_manifest() == sources
    summary = {**metadata, "ended_at": utc_now(), "records": rows, "executed_runs": len(rows),
               "inputs_and_sources_unchanged": unchanged,
               "status_counts": {status: sum(row["status"] == status for row in rows)
                                 for status in sorted({row["status"] for row in rows})}}
    summary["strict_pass"] = unchanged and len(rows) == metadata["planned_runs"] and all(row["status"] == "PASSED" for row in rows)
    write_json(suite / "summary.json", summary)
    return suite, summary["strict_pass"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scenarios-dir", "approval", "accounts", "base-url", "output-dir", "version"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    path, passed = run_panel(scenarios_dir=args.scenarios_dir, approval=args.approval,
        accounts_file=args.accounts, base_url=args.base_url, output_dir=args.output_dir,
        version=args.version, repetitions=args.repetitions, timeout=args.timeout)
    print(json.dumps({"artifact_directory": str(path), "strict_pass": passed}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
