"""Reproduce the fixed stabilization panel against explicit detached subjects.

This is a bounded experiment entry point, not a configurable mutation framework.
Run --verify before measurement. Worktrees and locked environments are prepared
separately; this script never changes a subject or installs a dependency.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/stabilization"
MANIFEST = FIXTURES / "manifest-r2.json"
ARCHIVED_EVIDENCE = {
    "manifest.json": "d8c5a3c69432a22ba0b39175b472edec17577c130bf6854f37d5f773b82da55f",
    "results.json": "9f580d408298d311a71c081cb54c1caf47e5ca9d0fbe2ae509983df457fbf5bc",
    "audit-results.json": "9f580d408298d311a71c081cb54c1caf47e5ca9d0fbe2ae509983df457fbf5bc",
}
REVISIONS = {"baseline": "67ce17f8855f976d138ee84e34e2df5fdde31cbe",
             "current": "936c50aee490ff9d97ec7ee8bbd207f94de5eda5"}
FAULTS = ("accepted_rejection", "changed_collection_target", "wrong_object_read")
OWN_SOURCES = ["scripts/measure_stabilization.py", "tests/stabilization_controls.py",
               "tests/test_stabilization_measurements.py",
               "tests/fixtures/stabilization/C01.patch", "tests/fixtures/stabilization/C02.patch"]
FROZEN = ["tests/include_fault_controls.py", "tests/include_fault_controls_baseline.json",
          "tests/include_fault_controls_candidate.json"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", "-C", str(cwd), *args])


def helper():
    spec = importlib.util.spec_from_file_location("stabilization_controls", ROOT / "tests/stabilization_controls.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_inventory(revision):
    paths = git("ls-tree", "-r", "--name-only", revision).decode().splitlines()
    selected = [p for p in paths if p.startswith(("refracto/", "adapters/documents/", "examples/documents/"))
                or p in FROZEN or p in {"tests/named_results_fault_controls.py", "pyproject.toml", "uv.lock"}
                or p in {"tests/test_documents_failure_continuation.py", "tests/test_field_comparison_consumers.py",
                         "tests/test_header_documents.py", "tests/test_member_reference_consumers.py",
                         "tests/test_numeric_check_consumers.py", "tests/test_rejection_evidence.py"}]
    return {path: digest(git("show", f"{revision}:{path}")) for path in selected}


def declaration_literals(revision):
    result = {}
    for path in ["tests/include_fault_controls.py", "tests/named_results_fault_controls.py"]:
        tree = ast.parse(git("show", f"{revision}:{path}"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                if node.value.value.startswith("schema_version:"):
                    result[path + "::" + node.targets[0].id] = digest(node.value.value.encode())
    return result


def manifest_template():
    """Construction-time output only: no service, Scenario run, or score."""
    sys.path.insert(0, str(ROOT))
    controls = helper()
    rows = []
    for row, (scenario, lane, reach, actions, failures) in controls.ROWS.items():
        rows.append({"id": row, "lane": lane, "scenario": controls.SCENARIOS + scenario,
                     "declaration_sha256": controls.fixture_hash(row),
                     "neighbor_expectation": controls.neighbor_expectation(row),
                     "fault_reach_count": reach, "fault_action_count": actions,
                     "required_failed_checks": [list(pair) for pair in failures],
                     "detector": "tests/stabilization_controls.py::" + ("engine_assertion" if lane == "engine" else "classify"),
                     "fault_layer": "engine" if lane == "engine" else "authenticator" if row == "G01" else "synthetic-target",
                     "baseline_applicability": "not_compared",
                     "patch": f"tests/fixtures/stabilization/{row}.patch" if lane == "engine" else None})
    historical = [{"revision": label, "fault": fault, "form": form, "injected": injected}
                  for label in REVISIONS for fault in FAULTS for form in ("flat", "include")
                  for injected in (False, True)]
    return {"manifest_version": 1, "projection": "backend", "revisions": REVISIONS,
            "historical_executions": historical, "current_rows": rows,
            "result_path": "tests/fixtures/stabilization/results-r2.json",
            "archived_evidence": ARCHIVED_EVIDENCE,
            "sources": {path: digest((ROOT / path).read_bytes()) for path in OWN_SOURCES},
            "subject_sources": {label: source_inventory(revision) for label, revision in REVISIONS.items()},
            "historical_declarations": {label: declaration_literals(revision) for label, revision in REVISIONS.items()},
            "frozen_historical_assets": {path: digest((ROOT / path).read_bytes()) for path in FROZEN}}


def verify_manifest():
    frozen = json.loads(MANIFEST.read_text())
    # Ordinary CI clones need not contain the old Git objects. Historical
    # source bytes are verified against their detached subject during measure().
    sys.path.insert(0, str(ROOT))
    controls = helper()
    if frozen["revisions"] != REVISIONS or frozen["manifest_version"] != 1 or frozen["projection"] != "backend":
        raise ValueError("unexpected frozen experiment identity")
    if frozen["archived_evidence"] != ARCHIVED_EVIDENCE:
        raise ValueError("archived measurement identity drift")
    for name, expected in ARCHIVED_EVIDENCE.items():
        if digest((FIXTURES / name).read_bytes()) != expected:
            raise ValueError("archived measurement changed: " + name)
    # Freeze the experiment, not all future core development. Exact historical
    # production-source hashes apply to detached reproduction subjects only.
    for group in (frozen["sources"], frozen["frozen_historical_assets"]):
        for name, expected in group.items():
            if digest((ROOT / name).read_bytes()) != expected:
                raise ValueError("frozen experiment source mismatch: " + name)
    expected_historical = [{"revision": label, "fault": fault, "form": form, "injected": injected}
                           for label in REVISIONS for fault in FAULTS for form in ("flat", "include")
                           for injected in (False, True)]
    if frozen["historical_executions"] != expected_historical:
        raise ValueError("historical execution inventory drift")
    if [item["id"] for item in frozen["current_rows"]] != list(controls.ROWS):
        raise ValueError("current row inventory drift")
    for item in frozen["current_rows"]:
        row = item["id"]
        scenario, lane, reach, actions, failures = controls.ROWS[row]
        actual = {"id": row, "lane": lane, "scenario": controls.SCENARIOS + scenario,
                  "declaration_sha256": controls.fixture_hash(row), "fault_reach_count": reach,
                  "neighbor_expectation": controls.neighbor_expectation(row),
                  "fault_action_count": actions, "required_failed_checks": [list(pair) for pair in failures],
                  "detector": "tests/stabilization_controls.py::" + ("engine_assertion" if lane == "engine" else "classify"),
                  "fault_layer": "engine" if lane == "engine" else "authenticator" if row == "G01" else "synthetic-target",
                  "baseline_applicability": "not_compared",
                  "patch": f"tests/fixtures/stabilization/{row}.patch" if lane == "engine" else None}
        if item != actual:
            raise ValueError("current control mapping drift: " + row)
    assert len(frozen["historical_executions"]) == 24
    assert len({canonical(item) for item in frozen["historical_executions"]}) == 24
    assert len(frozen["current_rows"]) == 14
    assert len({item["id"] for item in frozen["current_rows"]}) == 14
    return frozen


def worker(args):
    subject = Path(args.subject).resolve()
    sys.path.insert(0, str(subject))
    import refracto
    origin = Path(refracto.__file__).resolve()
    if origin.parent.parent != subject:
        raise RuntimeError("wrong import origin")
    metadata = {"revision": git("rev-parse", "HEAD", cwd=subject).decode().strip(),
                "import_origin": origin.relative_to(subject).as_posix(),
                "python": platform.python_version(),
                "dependencies": {p: importlib.metadata.version(p) for p in ("PyYAML", "pytest")}}
    if args.panel == "historical":
        from tests.named_results_fault_controls import run_control
        result = run_control(args.row, args.form, inject=args.inject)
        print(json.dumps({**metadata, "result": result}, sort_keys=True))
        return 0
    controls = helper()
    hits = []
    mutated = args.engine_mutant
    if mutated:
        filename = "refracto/projection/continuation.py" if args.row == "C01" else "refracto/report.py"
        lines = (subject / filename).read_text().splitlines()
        needle = "            self.stopper = step.id" if args.row == "C01" else "        if sts and sts[-1] == PASSED:"
        line = lines.index(needle) + (1 if args.row == "C01" else 2)
        def trace(frame, event, arg):
            if event == "line" and Path(frame.f_code.co_filename).resolve() == subject / filename and frame.f_lineno == line:
                hits.append({"file": filename, "line": line, "function": frame.f_code.co_name})
            return trace
        sys.settrace(trace)
    try:
        result = controls.observe(args.row, args.inject)
    finally:
        sys.settrace(None)
    output = {**metadata, "result": result, "mutated_branch_hits": hits}
    code = 0
    if args.row.startswith("C"):
        try:
            controls.engine_assertion(result, args.row)
        except AssertionError as error:
            output["assertion_failure"] = str(error)
            code = 1
    print(json.dumps(output, sort_keys=True))
    return code


def check_subject(path, revision, source_hashes, patch=None):
    path = path.resolve()
    if git("rev-parse", "HEAD", cwd=path).decode().strip() != revision:
        raise ValueError("unexpected subject revision")
    if subprocess.run(["git", "-C", str(path), "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode != 1:
        raise ValueError("subject must be a detached checkout")
    differences = git("diff", "--binary", cwd=path)
    if patch is None and differences:
        raise ValueError("unmutated subject has tracked differences")
    mutated_file = None
    if patch:
        mutated_file = "refracto/projection/continuation.py" if patch == "C01" else "refracto/report.py"
        names = git("diff", "--name-only", cwd=path).decode().splitlines()
        if names != [mutated_file]:
            raise ValueError("engine subject has unexpected changed files")
        subprocess.run(["git", "-C", str(path), "apply", "--reverse", "--check", str(FIXTURES / f"{patch}.patch")], check=True)
        original = git("show", f"{revision}:{mutated_file}", cwd=path)
        if digest(original) != source_hashes[mutated_file]:
            raise ValueError("engine baseline source hash mismatch")
        verify_engine_source(original, (path / mutated_file).read_bytes(), patch)
    for name, value in source_hashes.items():
        if name != mutated_file and digest((path / name).read_bytes()) != value:
            raise ValueError("subject source mismatch: " + name)
    return {"patch_sha256": digest((FIXTURES / f"{patch}.patch").read_bytes()) if patch else None,
            "mutated_source_sha256": digest((path / mutated_file).read_bytes()) if patch else None}


def engine_bytes(original, row):
    old, new = {
        "C01": (b'        if result.status in (ERROR, SKIPPED) or (result.status == FAILED and step.on_failure == "stop"):',
                b'        if result.status in (ERROR, SKIPPED, FAILED):'),
        "C02": (b'        sts = [s.status for s in self.steps]\n',
                b'        sts = [s.status for s in self.steps]\n        if sts and sts[-1] == PASSED:'
                b'\n            return PASSED\n'),
    }[row]
    if original.count(old) != 1:
        raise ValueError("engine mutation anchor is not unique")
    return original.replace(old, new, 1)


def verify_engine_source(original, actual, row):
    if actual != engine_bytes(original, row):
        raise ValueError("engine subject differs from the exact frozen mutation")


def record_key(record):
    return (record["subject"], record["panel"], record["row"], record["form"], record["injected"])


def expected_keys(manifest):
    keys = [(item["revision"], "historical", item["fault"], item["form"], item["injected"])
            for item in manifest["historical_executions"]]
    for item in manifest["current_rows"]:
        row = item["id"]
        if item["lane"] == "engine":
            keys.extend([("current", "engine", row, "flat", True), (row.lower(), "engine", row, "flat", True)])
        else:
            keys.extend(("current", "current", row, "flat", injected) for injected in (False, True))
    return keys


def outcome(record, neighbor, controls):
    result = record["result"]
    if record["panel"] != "engine" and record["exit_code"] != 0:
        return "invalid_control"
    try:
        if record["panel"] == "historical":
            valid = not any(status == "ERROR" for _, status in result["steps"])
            if not record["injected"]:
                ids = {"accepted_rejection": ["reject", "after"],
                       "changed_collection_target": ["create", "list", "after"],
                       "wrong_object_read": ["create", "read", "after"]}[record["row"]]
                complete = (result["fault_reached"] == 0 and len(result["requests"]) == len(ids)
                            and result["steps"] == [[step, "PASSED"] for step in ids])
                return "passing_neighbor" if valid and complete and result["status"] == "PASSED" and not result["degradations"] else "invalid_control"
            if outcome(neighbor, None, controls) != "passing_neighbor":
                return "invalid_control"
            if not valid:
                return "invalid_control"
            if result["fault_reached"] != 1:
                return "not_reached"
            expected = {"accepted_rejection": {"step": "reject", "check": "failure"},
                        "changed_collection_target": {"step": "list", "check": "collection_matching_count"},
                        "wrong_object_read": {"step": "read", "check": "field_equals"}}[record["row"]]
            return "detected" if result["status"] == "FAILED" and result["failures"] == [expected] else "missed"
        if record["panel"] == "current":
            if not record["injected"]:
                return "passing_neighbor" if controls.neighbor_valid(record["row"], result) else "invalid_control"
            if outcome(neighbor, None, controls) != "passing_neighbor":
                return "invalid_control"
            return controls.classify(record["row"], result, neighbor["result"])
        if record["subject"] == "current":
            if record["exit_code"] != 0 or not controls.neighbor_valid(record["row"], result):
                return "invalid_control"
            controls.engine_assertion(result, record["row"])
            return "passing_engine_control"
        if outcome(neighbor, None, controls) != "passing_engine_control":
            return "invalid_control"
        expected = {"C01": "C01: later read and delete must execute",
                    "C02": "C02: later success must not erase earlier failure"}[record["row"]]
        if record["exit_code"] == 1 and record.get("assertion_failure") == expected and record.get("mutated_branch_hits"):
            return "killed"
        return "survived" if record["exit_code"] == 0 else "invalid_control"
    except (KeyError, TypeError, AssertionError):
        return "invalid_control"


def recompute(records, manifest):
    """Reject missing/extra/duplicate units and derive—not trust—every outcome."""
    keys = [record_key(record) for record in records]
    if len(keys) != len(set(keys)) or set(keys) != set(expected_keys(manifest)):
        raise ValueError("execution keys do not match the exact frozen plan")
    sys.path.insert(0, str(ROOT))
    controls = helper()
    lookup = dict(zip(keys, records, strict=True))
    classifications = {}
    for key, record in lookup.items():
        subject, panel, row, form, injected = key
        label = subject if subject in REVISIONS else "current"
        if record.get("revision") != REVISIONS[label] or record.get("import_origin") != "refracto/__init__.py" or record["projection"] != "backend":
            classifications[key] = "invalid_control"
            continue
        neighbor = lookup.get(("current", "engine", row, form, True)) if panel == "engine" else lookup.get((subject, panel, row, form, False))
        classifications[key] = outcome(record, neighbor, controls)
    counts = {}
    for classification in classifications.values():
        counts[classification] = counts.get(classification, 0) + 1
    return classifications, counts


def audit_results(payload, manifest):
    if payload["manifest_sha256"] != digest(MANIFEST.read_bytes()):
        raise ValueError("result refers to a different manifest")
    classifications, counts = recompute(payload["records"], manifest)
    if payload["counts"] != counts:
        raise ValueError("saved counters differ from execution details")
    if any(record["result"]["classification"] != classifications[record_key(record)] for record in payload["records"]):
        raise ValueError("saved classification differs from observations")
    return counts


def measure(args):
    manifest = verify_manifest()
    output = Path(args.output or ROOT / manifest["result_path"])
    if output.exists():
        raise ValueError("result already exists; use a new --output path, never silently overwrite evidence")
    subjects = {key: Path(getattr(args, key)).resolve() for key in ("baseline", "current", "c01", "c02")}
    subject_evidence = {}
    for key, subject in subjects.items():
        label = key if key in REVISIONS else "current"
        subject_evidence[key] = check_subject(subject, REVISIONS[label], manifest["subject_sources"][label],
                                               key.upper() if key.startswith("c0") else None)
    records = []
    def execute(subject_key, panel, row, injected, form="flat", mutant=False):
        subject = subjects[subject_key]
        python = subject / ".venv/bin/python"
        argv = [str(python), "-I", str(Path(__file__).resolve()), "--worker", "--subject", str(subject),
                "--panel", panel, "--row", row, "--form", form]
        if injected:
            argv.append("--inject")
        if mutant:
            argv.append("--engine-mutant")
        with tempfile.TemporaryDirectory(prefix="refract-stabilization-invocation-") as directory:
            completed = subprocess.run(argv, cwd=directory, capture_output=True, text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            payload = json.loads(completed.stdout)
        except (ValueError, TypeError):
            payload = {"result": {"classification": "invalid_control"},
                       "worker_failure": "worker did not produce structured evidence"}
        record = {"subject": subject_key, "panel": panel, "row": row, "form": form,
                  "injected": injected, "projection": "backend", "exit_code": completed.returncode,
                  "command": ["$SUBJECT/.venv/bin/python", "-I", "$SOURCE/scripts/measure_stabilization.py",
                              *argv[3:]], **payload}
        record["command"] = ["$SUBJECT" if item == str(subject) else item for item in record["command"]]
        if completed.stderr:
            # Keep diagnostic evidence without disclosing host-specific paths.
            record["stderr"] = completed.stderr.replace(str(subject), "$SUBJECT").replace(str(ROOT), "$SOURCE")
        records.append(record)
        return record
    for item in manifest["historical_executions"]:
        execute(item["revision"], "historical", item["fault"], item["injected"], item["form"])
    for item in manifest["current_rows"]:
        row = item["id"]
        if item["lane"] != "engine":
            execute("current", "current", row, False)
            execute("current", "current", row, True)
        else:
            execute("current", "engine", row, True)
            execute(row.lower(), "engine", row, True, mutant=True)
    assert len(records) == 52
    classifications, counts = recompute(records, manifest)
    for record in records:
        record["result"]["classification"] = classifications[record_key(record)]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"result_version": 1, "manifest_sha256": digest(MANIFEST.read_bytes()),
                                 "subject_evidence": subject_evidence, "records": records, "counts": counts}, indent=2, sort_keys=True) + "\n")
    print(json.dumps(counts, sort_keys=True))
    return int(any(record["result"]["classification"] in {"invalid_control", "not_reached", "guard_missed"} for record in records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-template", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--subject")
    parser.add_argument("--panel")
    parser.add_argument("--row")
    parser.add_argument("--form", default="flat")
    parser.add_argument("--inject", action="store_true")
    parser.add_argument("--engine-mutant", action="store_true")
    for name in ("baseline", "current", "c01", "c02", "output"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if args.manifest_template:
        print(json.dumps(manifest_template(), indent=2, sort_keys=True))
        return 0
    if args.verify:
        verify_manifest()
        print("Frozen manifest verified: 24 historical executions and 14 current rows.")
        return 0
    if not all((args.baseline, args.current, args.c01, args.c02)):
        parser.error("measurement requires --baseline, --current, --c01 and --c02 detached subjects")
    return measure(args)


if __name__ == "__main__":
    raise SystemExit(main())
