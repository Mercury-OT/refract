"""Existing inclusion supports two explicit paths without a new Flow format."""
import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

from refracto.cli import main
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.runner import run_scenario


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "scenario-reuse"
PARENTS = ("create_update_read.yaml", "create_delete_read.yaml")
CHILD = "shared/create_item.yaml"
BASELINE_HASHES = {
    CHILD: "fa44aca218da484af1485cf6e80841edf20b124d1ce18c951acb78e9f011b145",
    "create_update_read.yaml": "bb1d67ca7a190cd704be88638bfbc687beaa7de3001c86edb50a1659bfd689fd",
    "create_update_read.includes.json": "9dd56dba70c186c5e9ab864530749e4dbc5b471d5a0318620f706cb8d022cb52",
}


def _snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _copy_selected_sources(tmp_path):
    """Select precisely two callers and their shared child, not the whole repo."""
    root = tmp_path / "parents"
    for name in (*PARENTS, CHILD, *(str(Path(name).with_suffix(".includes.json"))
                                   for name in PARENTS)):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((EXAMPLES / name).read_bytes())
    return root


def _forbid_runtime(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("declaration review attempted execution, network, or token generation")

    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("socket.getaddrinfo", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("uuid.uuid4", forbidden)
    # Guard the preceding local slice when present, without requiring it: these
    # static examples also run against the pre-run-values core.
    runner = sys.modules["refracto.runner"]
    if hasattr(runner, "bind_run_values"):
        monkeypatch.setattr(runner, "bind_run_values", forbidden)
    run_values = sys.modules.get("refracto.declaration.run_values")
    if run_values is not None:
        monkeypatch.setattr(run_values, "uuid4", forbidden)
    monkeypatch.setattr("refracto.runner.run_scenario", forbidden)


def test_existing_reviewed_sources_and_both_pins_are_unchanged():
    for name, expected_hash in BASELINE_HASHES.items():
        assert hashlib.sha256((EXAMPLES / name).read_bytes()).hexdigest() == expected_hash
    expected_pin = {"manifest_version": 1, "scenarios": {
        "shared.create_item": {"path": CHILD, "sha256": BASELINE_HASHES[CHILD]}}}
    for name in PARENTS:
        sidecar = (EXAMPLES / name).with_suffix(".includes.json")
        assert json.loads(sidecar.read_text()) == expected_pin


def test_new_parent_matches_the_approved_deletion_obligations():
    actual = yaml.safe_load((EXAMPLES / "create_delete_read.yaml").read_text())
    created_id = {"from_step": "create", "result": "record_id"}
    assert actual == {
        "schema_version": 1,
        "scenario": "demo.create_delete_read",
        "description": "Create, delete, then confirm that the created item is absent from the list.",
        "users": ["user"],
        "parameters": {"record_name": "Delete test record"},
        "steps": [
            {"id": "create", "do": {"include": "shared.create_item"},
             "with": {"item_name": {"from_parameter": "record_name"}}},
            {"id": "delete", "do": {"request": {"method": "DELETE", "path": ["items", created_id]}},
             "expect": {
                 "response": [{"check": "success"},
                              {"check": "field_equals", "field": "deleted", "value": 1}],
                 "backend_state": [{"check": "span_exists", "span": "item.delete"}]}},
            {"id": "read", "do": {"request": {"method": "GET", "path": ["items"]}},
             "expect": {"response": [{"check": "success"}, {
                 "check": "collection_matching_count", "field": "items",
                 "matching": {"id": created_id}, "count": 0}]}},
        ],
    }


@pytest.mark.parametrize("name", PARENTS)
def test_validate_and_expansion_preserve_child_checks_users_and_results_without_execution(
        name, monkeypatch, capsys):
    _forbid_runtime(monkeypatch)
    before = _snapshot(EXAMPLES)
    path = EXAMPLES / name
    assert main(["validate", str(path)]) == 0
    assert f"OK demo.{Path(name).stem}" in capsys.readouterr().out
    assert main(["validate", str(path), "--expand"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["view"] == "expanded-review/1"
    assert [step["id"] for step in view["steps"]] == [
        "create/create_request", "update" if name == PARENTS[0] else "delete", "read"]
    assert view["include_user_mappings"] == {"create": {"user": "user"}}
    assert all(step["user"] == "user" and step["session"] == "reuse" for step in view["steps"])
    assert view["included_results"] == {"create": {
        "record_id": {"from_step": "create/create_request", "response_field": "itemId"},
        "record_name": {"from_step": "create/create_request", "response_field": "name"},
    }}
    first = view["steps"][0]
    assert first["source"] == {
        "scenario_id": "shared.create_item", "step_id": "create_request",
        "include_step_id": "create", "sha256": BASELINE_HASHES[CHILD],
        "source_user": "user", "effective_user": "user",
    }
    literal = lambda value: {"kind": "literal", "value": value}
    assert first["expect"] == {
        "response": [{"check": "success"}, {"check": "has", "field": literal("itemId")},
                     {"check": "field_equals", "field": literal("name"),
                      "value": {"kind": "reference", "from_parameter": "@include:create:0"}}],
        "backend_state": [{"check": "span_exists", "span": literal("item.create")}],
    }
    parent = load_scenario(path)
    child = load_scenario(EXAMPLES / CHILD)
    parent_create, bindings = prepare_step(parent.steps[0], parent, {})
    assert bindings == {}
    child_expected_name = "Test record" if name == PARENTS[0] else "Delete test record"
    assert parent_create.request.body == {"name": child_expected_name}
    assert parent_create.expect.response[-1].params == {"field": "name", "value": child_expected_name}
    assert [(a.check, a.params) for a in parent_create.expect.backend_state] == [
        (a.check, a.params) for a in child.steps[0].expect.backend_state]
    assert all(not getattr(scenario, "run_values_bound", False) for scenario in (parent, child))
    assert _snapshot(EXAMPLES) == before


@pytest.mark.parametrize("name", PARENTS)
@pytest.mark.parametrize("defect,message", [
    ("unknown-result", "earlier include's declared result"),
    ("undeclared-user", "step.user must name a declared user"),
    ("stale-pin", "fingerprint mismatch"),
])
def test_invalid_caller_is_rejected_before_authentication_request_or_token(
        tmp_path, monkeypatch, capsys, name, defect, message):
    root = _copy_selected_sources(tmp_path)
    path = root / name
    if defect == "stale-pin":
        child = root / CHILD
        child.write_bytes(child.read_bytes() + b"\n# Candidate change, not a renewed approval.\n")
    else:
        document = yaml.safe_load(path.read_text())
        if defect == "unknown-result":
            document["steps"][1]["do"]["request"]["path"][1]["result"] = "unpublished_id"
        else:
            document["steps"][1]["user"] = "undeclared_participant"
        path.write_text(yaml.safe_dump(document, sort_keys=False))
    _forbid_runtime(monkeypatch)
    before = _snapshot(tmp_path)
    assert main(["validate", str(path)]) == 2
    assert message in capsys.readouterr().err
    accessed = []

    class NoAdapters:
        def __getattr__(self, attribute):
            accessed.append(attribute)
            pytest.fail("invalid source reached an adapter before full declaration validation")

    # The imported function is the real runner, not the patched CLI guard.
    with pytest.raises(DeclarationError, match=message):
        run_scenario(path, NoAdapters(), projections=("backend",))
    assert accessed == []
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("change", ["child-bytes", "consumed-result-removed"])
def test_existing_impact_cli_finds_both_callers_without_repinning_or_execution(
        tmp_path, monkeypatch, capsys, change):
    root = _copy_selected_sources(tmp_path)
    after = root / CHILD
    before_path = tmp_path / "before.yaml"
    before_path.write_bytes(after.read_bytes())
    if change == "child-bytes":
        after.write_bytes(after.read_bytes() + b"\n# Candidate documentation change.\n")
    else:
        candidate = yaml.safe_load(after.read_text())
        del candidate["results"]["record_id"]
        after.write_text(yaml.safe_dump(candidate, sort_keys=False))
    _forbid_runtime(monkeypatch)
    before = _snapshot(tmp_path)
    command = ["impact", "--before", str(before_path), "--after", str(after),
               "--parents", str(root), "--json"]
    assert main(command) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "COMPLETE" and report["review_required"] is True
    assert report["scope"]["yaml_files_discovered"] == 3
    assert report["target"]["bytes_changed"] is True
    assert {item["path"] for item in report["parents"]} == set(PARENTS)
    for caller in report["parents"]:
        assert caller["validity"] == {
            "actual": "invalid", "hypothetical_before": "valid",
            "hypothetical_after": "valid" if change == "child-bytes" else "invalid",
        }
        assert len(caller["includes"]) == 1
        included = caller["includes"][0]
        assert included["pin_match"] == "before"
        assert included["expected_pin"] == BASELINE_HASHES[CHILD]
        assert included["actual_sha256"] == hashlib.sha256(after.read_bytes()).hexdigest()
        assert included["user_binding"]["effective_user"] == "user"
        assert {consumer["result"] for consumer in included["consumers"]} == {"record_id"}
        assert {consumer["step_id"] for consumer in included["consumers"]} == {
            "read", "update" if caller["path"] == PARENTS[0] else "delete"}
        with pytest.raises(DeclarationError, match="fingerprint mismatch"):
            load_scenario(root / caller["path"])
    if change == "consumed-result-removed":
        assert {"location": "/results/record_id", "kind": "removed"}.items() <= next(
            entry.items() for entry in report["changes"] if entry["location"] == "/results/record_id")
    else:
        assert report["target"]["structure_changed"] is False
        assert report["changes"] == []
    assert main(command) == 1
    assert json.loads(capsys.readouterr().out) == report
    assert _snapshot(tmp_path) == before
