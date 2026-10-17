"""Offline change review is explicit, bounded, typed, and never approval."""
import copy
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from refracto.cli import main
from refracto.declaration.impact import Limits, exit_code, inspect_impact, render_text
from refracto.declaration.loader import DeclarationError, load_scenario


def child(**changes):
    document = {
        "schema_version": 1, "scenario": "shared.create", "actor": "user",
        "parameters": {"name": "Default record"},
        "steps": [{"id": "create", "do": {"request": {
            "method": "POST", "path": ["items"], "body": {"name": {"from_parameter": "name"}}}},
            "expect": {"response": [{"check": "success"}, {"check": "has", "field": "id"},
                                      {"check": "field_equals", "field": "name", "value": {"from_parameter": "name"}}]}}],
        "results": {"record_id": {"from_step": "create", "response_field": "id"}},
    }
    document.update(changes)
    return document


def include(sid="setup", target="shared.create", **fields):
    return {"id": sid, "do": {"include": target}, **fields}


def reference(sid="setup", result="record_id"):
    return {"from_step": sid, "result": result}


def parent(steps=None, **changes):
    document = {"schema_version": 1, "scenario": "example.parent", "actor": "user",
                "steps": steps or [include(), {"id": "read", "do": {"request": {
                    "method": "GET", "path": ["items", reference()]}},
                    "expect": {"response": [{"check": "success"}]}}]}
    document.update(changes)
    return document


def write_yaml(path, document):
    class NoAliases(yaml.SafeDumper):
        def ignore_aliases(self, value):
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(document, Dumper=NoAliases, sort_keys=False), encoding="utf-8")
    return path


def pin(parent_path, targets):
    entries = {sid: {"path": path.relative_to(parent_path.parent).as_posix(),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for sid, path in targets.items()}
    parent_path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1, "scenarios": entries}), encoding="utf-8")


def bundle(tmp_path, old=None, new=None, caller=None):
    root = tmp_path / "scenarios"
    old = child() if old is None else old
    before = write_yaml(tmp_path / "before.yaml", old)
    after = write_yaml(root / "shared" / "child.yaml", old)
    call = write_yaml(root / "parent.yaml", parent() if caller is None else caller)
    pin(call, {"shared.create": after})
    if new is not None:
        write_yaml(after, new)
    return before, after, root, call


def inspect(paths, **kwargs):
    return inspect_impact(*paths[:3], **kwargs)


def test_report_contract_clean_same_file_and_no_caller_scope(tmp_path):
    paths = bundle(tmp_path)
    report = inspect(paths)
    assert set(report) == {"report_version", "status", "review_required", "scope", "target", "changes", "parents", "gaps"}
    assert report["report_version"] == 1
    assert report["status"] == "COMPLETE" and not report["review_required"]
    assert exit_code(report) == 0
    assert report["target"]["bytes_changed"] is report["target"]["structure_changed"] is False
    assert report["parents"][0]["validity"] == {"actual": "valid", "hypothetical_before": "valid", "hypothetical_after": "valid"}
    assert inspect_impact(paths[1], paths[1], paths[2])["status"] == "COMPLETE"
    no_calls = inspect_impact(paths[0], paths[1], paths[1].parent)
    assert no_calls["status"] == "COMPLETE" and no_calls["parents"] == []


def test_multiple_parents_sites_and_same_id_other_file(tmp_path):
    paths = bundle(tmp_path, caller=parent([include("first"), include("second")]))
    before, after, root, _ = paths
    other_parent = write_yaml(root / "another.yml", parent())
    pin(other_parent, {"shared.create": after})
    copy_child = write_yaml(root / "copy" / "child.yaml", child())
    unrelated = write_yaml(root / "copy" / "caller.yaml", parent())
    pin(unrelated, {"shared.create": copy_child})
    report = inspect(paths)
    assert report["status"] == "COMPLETE"
    assert [item["path"] for item in report["parents"]] == ["another.yml", "parent.yaml"]
    assert [site["step_id"] for site in report["parents"][1]["includes"]] == ["first", "second"]
    assert report["scope"]["yaml_files_discovered"] == 5


@pytest.mark.parametrize("change", ["result", "actor", "parameter"])
def test_known_breakage_is_complete_but_actual_pin_stays_invalid(tmp_path, change):
    new = child()
    caller = parent([include(**{"with": {"name": "Chosen"}}), parent()["steps"][1]])
    if change == "result":
        new["results"] = {}
    elif change == "actor":
        new["actor"] = "different-role"
    else:
        new["parameters"] = {}
        new["steps"][0]["do"]["request"]["body"]["name"] = "Fixed"
        new["steps"][0]["expect"]["response"][-1]["value"] = "Fixed"
    paths = bundle(tmp_path, new=new, caller=caller)
    report = inspect(paths)
    assert report["status"] == "COMPLETE" and exit_code(report) == 1
    assert report["parents"][0]["validity"] == {"actual": "invalid", "hypothetical_before": "valid", "hypothetical_after": "invalid"}
    assert report["parents"][0]["includes"][0]["pin_match"] == "before"
    with pytest.raises(DeclarationError, match="fingerprint mismatch"):
        load_scenario(paths[3])


def test_updated_actual_pin_and_new_result_not_consumed(tmp_path):
    new = child()
    new["results"]["record_name"] = {"from_step": "create", "response_field": "name"}
    paths = bundle(tmp_path, new=new)
    pin(paths[3], {"shared.create": paths[1]})
    report = inspect(paths)
    assert report["status"] == "COMPLETE" and exit_code(report) == 1
    assert set(report["parents"][0]["validity"].values()) == {"valid"}
    assert report["parents"][0]["includes"][0]["pin_match"] == "after"
    assert any(change["location"] == "/results/record_name" and change["kind"] == "added" for change in report["changes"])


@pytest.mark.parametrize("before_value,after_value", [(False, 0), (True, 1), (1, 1.0), (None, "")])
def test_strict_types_and_changed_defaults(tmp_path, before_value, after_value):
    paths = bundle(tmp_path, old=child(parameters={"name": before_value}), new=child(parameters={"name": after_value}))
    report = inspect(paths)
    assert report["target"]["structure_changed"] is True
    change = next(c for c in report["changes"] if c["location"] == "/parameters/name")
    assert change["before"]["type"] != change["after"]["type"]
    assert "value" not in change["before"] and "value" not in change["after"]
    defaults = report["parents"][0]["includes"][0]["defaults"]
    assert defaults["before"]["name"] == change["before"]
    assert defaults["after"]["name"] == change["after"]


@pytest.mark.parametrize("format_only", ["comment", "mapping-order"])
def test_byte_only_changes_still_require_review(tmp_path, format_only):
    paths = bundle(tmp_path)
    if format_only == "comment":
        paths[1].write_text(paths[1].read_text() + "\n# reviewed formatting change\n")
    else:
        paths[1].write_text(yaml.safe_dump(child(), sort_keys=True))
    report = inspect(paths)
    assert report["target"]["bytes_changed"] is True
    assert report["target"]["structure_changed"] is False
    assert report["changes"] == [] and exit_code(report) == 1


def test_step_order_assertion_order_and_action_poll_changes(tmp_path):
    old = child()
    old["steps"].append({"id": "pause", "do": "wait", "duration": 1})
    new = copy.deepcopy(old)
    new["steps"].reverse()
    new["steps"][0]["duration"] = 2
    new["steps"][1]["do"]["request"]["method"] = "GET"
    new["steps"][1]["poll"] = {"on_timeout": "FAIL"}
    new["steps"][1]["expect"]["response"].reverse()
    report = inspect(bundle(tmp_path, old=old, new=new))
    locations = {row["location"] for row in report["changes"]}
    assert "/steps" in locations and "/steps/by-id/pause/duration" in locations
    assert "/steps/by-id/create/do/request/method" in locations and "/steps/by-id/create/poll" in locations
    assert any("/expect/response/" in path for path in locations)
    assert exit_code(report) == 1


def test_internal_rename_is_added_removed_not_inferred_safe(tmp_path):
    new = child()
    new["steps"][0]["id"] = "persist"
    new["results"]["record_id"]["from_step"] = "persist"
    report = inspect(bundle(tmp_path, new=new))
    assert ("/steps/by-id/create", "removed") in {(c["location"], c["kind"]) for c in report["changes"]}
    assert ("/steps/by-id/persist", "added") in {(c["location"], c["kind"]) for c in report["changes"]}
    assert report["parents"][0]["validity"]["hypothetical_after"] == "valid"


def test_assertion_removal_is_fact_not_automatic_incompatibility(tmp_path):
    new = child()
    new["steps"][0]["expect"]["response"].pop()
    report = inspect(bundle(tmp_path, new=new))
    assert any(c["kind"] == "removed" and "/expect/response/" in c["location"] for c in report["changes"])
    assert report["parents"][0]["validity"]["hypothetical_after"] == "valid"
    assert "weaker" not in json.dumps(report)


def test_consumers_all_grammar_positions_and_literal_defaults(tmp_path):
    ref = reference()
    steps = [include(),
             {"id": "fill", "do": "fill", "target": "name", "value": ref},
             {"id": "send", "do": {"request": {"method": "POST", "path": ["items", ref], "body": {"id": ref}}},
              "expect": {"response": [{"check": "field_equals", "field": "id", "value": ref},
                                        {"check": "collection_matching_count", "field": "items", "matching": {"id": ref}, "count": 1}],
                         "backend_state": [{"check": "span_attr", "span": "create", "attr": "id", "op": "==", "value": ref}]}},
             {"id": "click", "do": "click", "target": "submit", "expect": {
                 "request": {"method": "POST", "path": ["items", ref], "body": {"id": ref}},
                 "ui": [{"check": "object_field_equals", "anchor": "items", "id": ref, "field": "id", "value": ref}]}},
             include("second", **{"with": {"name": ref}}),
             {"id": "literal", "do": {"request": {"method": "POST", "path": ["items"], "body": {"payload": {"from_parameter": "payload"}}}}}]
    caller = parent(steps, parameters={"payload": ref}, description="from_step setup result record_id")
    report = inspect(bundle(tmp_path, caller=caller))
    assert report["status"] == "COMPLETE"
    sites = report["parents"][0]["includes"]
    consumers = sites[0]["consumers"]
    assert len(consumers) == 11
    assert {c["step_id"] for c in consumers} == {"fill", "send", "click", "second"}
    assert all(c["result"] == "record_id" for c in consumers)
    assert sites[1]["consumers"] == []
    assert sites[1]["with"]["name"] == {"kind": "step-reference", "from_step": "setup", "result": "record_id"}


def test_with_default_provenance_and_current_parent_only(tmp_path):
    caller = parent([include(**{"with": {"name": {"from_parameter": "chosen"}}}), parent()["steps"][1]], parameters={"chosen": "Caller value"})
    paths = bundle(tmp_path, new=child(parameters={"name": "New default", "unused": False}), caller=caller)
    report = inspect(paths)
    site = report["parents"][0]["includes"][0]
    assert site["defaults"] == {"before": {}, "after": {"unused": {"type": "boolean"}}}
    assert site["with"] == {"name": {"kind": "parameter-reference", "from_parameter": "chosen"}}
    assert "CURRENT" in render_text(report) and "not historical replay" in render_text(report)


@pytest.mark.parametrize("mutation,code", [
    ("missing-before", "missing-input"), ("missing-root", "missing-input"),
    ("missing-after", "missing-input"), ("missing-sidecar", "missing-input"),
    ("id-change", "target-id-changed"), ("unknown-pin", "selected-pin-unknown"),
    ("extra-sidecar", "invalid-sidecar"), ("wrong-sidecar-type", "invalid-sidecar"),
    ("duplicate-sidecar", "invalid-sidecar"), ("extra-target", "invalid-sidecar"),
    ("invalid-parent", "invalid-before-parent"), ("nested-child", "invalid-child"),
])
def test_missing_invalid_and_unknown_evidence_never_clean(tmp_path, mutation, code):
    paths = list(bundle(tmp_path))
    sidecar = paths[3].with_suffix(".includes.json")
    if mutation == "missing-before":
        paths[0] = tmp_path / "absent.yaml"
    elif mutation == "missing-root":
        paths[2] = tmp_path / "absent"
    elif mutation == "missing-after":
        paths[1] = paths[2] / "absent.yaml"
    elif mutation == "missing-sidecar":
        sidecar.unlink()
    elif mutation == "id-change":
        write_yaml(paths[1], child(scenario="renamed"))
    elif mutation in {"unknown-pin", "extra-sidecar", "wrong-sidecar-type", "extra-target"}:
        data = json.loads(sidecar.read_text())
        if mutation == "unknown-pin":
            data["scenarios"]["shared.create"]["sha256"] = "0" * 64
        elif mutation == "extra-sidecar":
            data["extra"] = True
        elif mutation == "wrong-sidecar-type":
            data["manifest_version"] = True
        else:
            data["scenarios"]["unused"] = copy.deepcopy(data["scenarios"]["shared.create"])
        sidecar.write_text(json.dumps(data))
    elif mutation == "duplicate-sidecar":
        sidecar.write_text('{"manifest_version": 1, "manifest_version": 1, "scenarios": {}}')
    elif mutation == "invalid-parent":
        write_yaml(paths[3], parent([include(), {"id": "read", "do": {"request": {"method": "GET", "path": ["items", reference(result="missing")]}}}]))
    else:
        write_yaml(paths[1], child(steps=[include("nested", "other.child")]))
    report = inspect(paths)
    assert report["status"] == "INCOMPLETE" and report["review_required"] and exit_code(report) == 2
    assert code in {g["code"] for g in report["gaps"]}


@pytest.mark.parametrize("source", ["", "null", "[]", "schema_version: 1\nschema_version: 1\n", "!!python/object/apply:os.system ['DO-NOT-EXECUTE']", "x: &x []\ny: *x\n", "1: non-string\n", "scenario: [\n"])
def test_unselected_bad_yaml_is_gap(tmp_path, source):
    paths = bundle(tmp_path)
    (paths[2] / "bad.yaml").write_text(source)
    report = inspect(paths)
    assert report["status"] == "INCOMPLETE" and exit_code(report) == 2
    assert any(g["location"] == "bad.yaml" for g in report["gaps"])


def test_other_dependency_drift_is_gap_with_located_selected_call(tmp_path):
    paths = bundle(tmp_path, caller=parent([include(), include("other", "shared.other")]))
    other = write_yaml(paths[2] / "shared" / "other.yaml", child(scenario="shared.other"))
    pin(paths[3], {"shared.create": paths[1], "shared.other": other})
    other.write_text(other.read_text() + "\n# changed\n")
    report = inspect(paths)
    assert report["status"] == "INCOMPLETE"
    assert report["parents"][0]["includes"][0]["step_id"] == "setup"
    assert report["parents"][0]["validity"] == {"actual": "unknown", "hypothetical_before": "unknown", "hypothetical_after": "unknown"}
    assert "non-target-pin-mismatch" in {g["code"] for g in report["gaps"]}


@pytest.mark.parametrize("declared", ["../before.yaml", "/outside.yaml", "shared/missing.yaml", "https://example.com/child.yaml", "shared/./child.yaml"])
def test_unsafe_and_missing_dependency(tmp_path, declared):
    paths = bundle(tmp_path)
    sidecar = paths[3].with_suffix(".includes.json")
    data = json.loads(sidecar.read_text())
    data["scenarios"]["shared.create"]["path"] = declared
    sidecar.write_text(json.dumps(data))
    report = inspect(paths)
    assert exit_code(report) == 2
    assert "unsafe-or-missing-dependency" in {g["code"] for g in report["gaps"]}


@pytest.mark.parametrize("location", ["root", "before", "after", "sidecar", "directory", "unrelated"])
def test_symlinks_are_never_followed(tmp_path, location):
    paths = list(bundle(tmp_path))
    if location in {"root", "before", "after"}:
        index = {"root": 2, "before": 0, "after": 1}[location]
        original = paths[index]
        linked = original.with_name("linked" + original.suffix)
        linked.symlink_to(original, target_is_directory=original.is_dir())
        paths[index] = linked
    elif location == "sidecar":
        original = paths[3].with_suffix(".includes.json")
        moved = original.with_suffix(".saved")
        original.rename(moved)
        original.symlink_to(moved)
    else:
        (paths[2] / "link").symlink_to(tmp_path if location == "directory" else paths[0], target_is_directory=location == "directory")
    assert exit_code(inspect(paths)) == 2


@pytest.mark.parametrize("field", ["entries", "yaml_files", "files", "file_bytes", "total_bytes"])
def test_resource_limits_inclusive_boundary_and_above(tmp_path, field):
    paths = bundle(tmp_path)
    report = inspect(paths)
    scope = report["scope"]
    bound = {"entries": scope["directory_entries_inspected"], "yaml_files": scope["yaml_files_discovered"],
             "files": scope["files_captured"], "file_bytes": max(p.stat().st_size for p in [paths[0], paths[1], paths[3], paths[3].with_suffix(".includes.json")]),
             "total_bytes": scope["bytes_captured"]}[field]
    assert exit_code(inspect(paths, limits=replace(Limits(), **{field: bound}))) == 0
    above = inspect(paths, limits=replace(Limits(), **{field: bound - 1}))
    assert exit_code(above) == 2 and above["review_required"]


def test_default_output_and_errors_hide_literals_show_values_is_explicit(tmp_path, capsys):
    secret = "SENSITIVE-LITERAL-SENTINEL"
    paths = bundle(tmp_path, old=child(parameters={"name": secret}), new=child(parameters={"name": secret + "-new"}),
                   caller=parent([include(**{"with": {"name": secret}}), parent()["steps"][1]]))
    args = ["impact", "--before", str(paths[0]), "--after", str(paths[1]), "--parents", str(paths[2])]
    assert main(args) == 1
    assert secret not in capsys.readouterr().out
    assert main(args + ["--json"]) == 1
    assert secret not in capsys.readouterr().out
    assert main(args + ["--json", "--show-values"]) == 1
    assert secret in capsys.readouterr().out
    (paths[2] / "bad.yaml").write_text(f"x: 1\nx: {secret}\n")
    assert main(args + ["--json"]) == 2
    assert secret not in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["impact", "--help"])
    assert exc.value.code == 0 and "source confidentiality" in " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("bad", ["timestamp", "scenario-id", "step-id", "nan", "nested-inf"])
def test_malformed_parent_metadata_cannot_crash_or_echo_values(tmp_path, bad):
    secret = "SENSITIVE-MALFORMED-SENTINEL"
    caller = parent()
    if bad == "scenario-id":
        caller["scenario"] = {"secret": secret}
    elif bad == "step-id":
        caller["steps"][0]["id"] = [secret]
    elif bad in {"nan", "nested-inf"}:
        caller["steps"][0]["with"] = {"name": float("nan") if bad == "nan" else {"nested": float("inf")}}
    paths = bundle(tmp_path, caller=caller)
    if bad == "timestamp":
        paths[3].write_text(paths[3].read_text().replace("include: shared.create", "include: shared.create\n  with:\n    name: 2026-01-01"))
    report = inspect(paths, show_values=True)
    assert exit_code(report) == 2
    serialized = json.dumps(report, allow_nan=False)
    assert secret not in serialized


def test_read_once_deterministic_unchanged_inputs_no_runtime(tmp_path, monkeypatch):
    paths = bundle(tmp_path, caller=parent([include("one"), include("two")]))
    before_tree = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    opened = {}
    original = Path.open

    def observed(path, *args, **kwargs):
        assert (args[0] if args else kwargs.get("mode", "r")) == "rb"
        opened[path] = opened.get(path, 0) + 1
        return original(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("review attempted process, network, or execution")

    monkeypatch.setattr(Path, "open", observed)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("refracto.runner.run_scenario", forbidden)
    first = inspect(paths)
    assert len(opened) == first["scope"]["files_captured"]
    assert set(opened.values()) == {1}
    opened.clear()
    assert inspect(paths) == first
    assert set(opened.values()) == {1}
    monkeypatch.setattr(Path, "open", original)
    after_tree = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before_tree == after_tree


def test_unreadable_capture_and_outside_target_are_explicit(tmp_path, monkeypatch):
    paths = bundle(tmp_path)
    original = Path.open

    def denied(path, *args, **kwargs):
        if path == paths[0]:
            raise PermissionError("SENSITIVE-OS-ERROR")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    report = inspect(paths)
    assert exit_code(report) == 2 and "SENSITIVE-OS-ERROR" not in json.dumps(report)
    monkeypatch.setattr(Path, "open", original)
    outside = inspect_impact(paths[1], paths[0], paths[2])
    assert exit_code(outside) == 2 and "target-outside-root" in {g["code"] for g in outside["gaps"]}


def test_deep_directory_tree_does_not_use_python_recursion(tmp_path):
    paths = bundle(tmp_path)
    directory = paths[2]
    for _ in range(140):
        directory /= "d"
        directory.mkdir()
    previous = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(120)
        report = inspect(paths)
    finally:
        sys.setrecursionlimit(previous)
    assert report["status"] == "COMPLETE" and exit_code(report) == 0
    assert report["scope"]["directory_entries_inspected"] > 140


def test_cli_argument_error_and_missing_inputs_report(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["impact", "--before", "old.yaml"])
    assert exc.value.code == 2
    capsys.readouterr()
    args = ["impact", "--before", str(tmp_path / "old.yaml"), "--after", str(tmp_path / "new.yaml"), "--parents", str(tmp_path), "--json"]
    assert main(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["target"]["scenario_id"] is None
    assert report["target"]["bytes_changed"] is None and report["parents"] == []


def test_existing_validate_and_expand_unchanged(tmp_path, capsys):
    paths = bundle(tmp_path)
    assert main(["validate", str(paths[3])]) == 0
    assert "OK example.parent" in capsys.readouterr().out
    assert main(["validate", str(paths[3]), "--expand"]) == 0
    assert json.loads(capsys.readouterr().out)["view"] == "expanded-review/1"
