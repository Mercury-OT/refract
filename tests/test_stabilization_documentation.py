"""Exhaustive current-contract fragments and exact linked-example consumers.

These checks validate real document text, not a second copy of its declarations.
Consumer collection is not consumer execution; the normal full-suite CI runs the
listed tests, including the optional real HTTP/browser tests.
"""
from dataclasses import dataclass
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from textwrap import indent
import tomllib

import pytest
import yaml

from refracto.declaration.loader import DeclarationError, load_scenario


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "SCENARIO.md"

# Each signature identifies a context, never a copied declaration. Unknown,
# duplicate and missing fences require an explicit inventory decision.
CONTEXTS = {
    "query": "- id: next_page\n",
    "headers": "- id: submit\n",
    "comparison": "- check: field_equals\n",
    "numeric_length": "- check: field_compare\n",
    "status_equals": "- check: status_equals\n",
    "status_in": "- check: status_in\n",
    "collection": "- id: read_list\n",
    "dictionary": "from_step: create\n",
    "member": "from_step: locate\n",
    "run_parameters": "parameters:\n  run_token: {from_run: unique}\n",
    "literal_parameters": "parameters:\n  payload:\n    literal:\n",
    "time_parameters": "parameters:\n  expires_at: {from_run: time, offset: {days: 7}}\n",
    "response_concat": "concat:\n",
    "include": "- id: setup\n",
    "mapped_include": "- id: access\n",
    "results": "results:\n",
    "poll": "schema_version: 1\nscenario: demo.export_ready\n",
    "stop": "- id: verify_before_next_action\n",
    "ui": "schema_version: 1\nscenario: demo.record_create\n",
}


def yaml_fences(text):
    """Read all Markdown YAML/YML fences, not just unindented triple backticks."""
    blocks, opened, lines = [], None, []
    for line in text.splitlines(keepends=True):
        if opened is None:
            match = re.fullmatch(r" {0,3}(`{3,}|~{3,})([^\n]*)\n?", line)
            if match:
                marker, info = match.groups()
                language = info.strip().split(maxsplit=1)
                opened = (marker[0], len(marker), language[0].lower() if language else "")
                lines = []
        elif re.fullmatch(r" {0,3}" + re.escape(opened[0]) +
                          "{" + str(opened[1]) + r",}[ \t]*\n?", line):
            if opened[2] in {"yaml", "yml"}:
                blocks.append("".join(lines))
            opened = None
        else:
            lines.append(line)
    assert opened is None, "Unclosed Markdown fence"
    return blocks


def inventory(text):
    blocks = {}
    for body in yaml_fences(text):
        matching = [name for name, prefix in CONTEXTS.items() if body.startswith(prefix)]
        assert len(matching) == 1, "Uninventoried or ambiguous YAML fence"
        name = matching[0]
        assert name not in blocks, f"Duplicate YAML fence: {name}"
        blocks[name] = body
    assert set(blocks) == set(CONTEXTS), "Missing YAML fence/context"
    return blocks


def request(step_id):
    return {"id": step_id, "do": {"request": {"method": "GET", "path": ["records"]}},
            "expect": {"response": [{"check": "success"}]}}


def render_context(name, body):
    """Insert untouched body bytes into a bounded surrounding declaration.

    Do not safe_load/safe_dump the fragment: that could erase duplicate keys and
    silently turn invalid documentation into a different valid declaration.
    """
    if name in {"poll", "ui"}:
        return body
    metadata = {"schema_version": 1, "scenario": "demo.documented_context", "users": ["owner"]}
    parameters = {
        "query": {"category": "guide"},
        "headers": {"idempotency_key": "fixed-example-key", "record_name": "Example record"},
        "comparison": {"attempted_content": {"title": "Changed"}},
        "numeric_length": {"page_size": 1},
        "collection": {"record_name": "Example record"},
        "member": {"record_code": "B"},
        "include": {"record_name": "Example record"},
    }
    if name in parameters:
        metadata["parameters"] = parameters[name]
    if name == "mapped_include":
        metadata["users"] = ["creator", "anonymous"]
    prefix = yaml.safe_dump(metadata, sort_keys=False)
    if name == "time_parameters":
        return prefix + body + (
            "steps:\n  - id: query\n    do:\n      request:\n        method: GET\n"
            "        path: [records]\n        query:\n"
            "          start: {from_parameter: window_start}\n"
            "          end: {from_parameter: window_end}\n"
            "    expect:\n      response:\n        - check: status_equals\n          value: 200\n")
    if name == "run_parameters":
        return prefix + body + (
            "steps:\n  - id: create\n    do:\n      request:\n        method: POST\n"
            "        path: [records]\n        body:\n"
            "          title: {from_parameter: document_title}\n"
            "    expect:\n      response:\n        - check: success\n")
    if name == "literal_parameters":
        return prefix + body + (
            "steps:\n  - id: send\n    do:\n      request:\n        method: POST\n"
            "        path: [records]\n        body:\n"
            "          payload: {from_parameter: payload}\n"
            "    expect:\n      response:\n        - check: success\n")
    if name == "response_concat":
        prior = indent(yaml.safe_dump([request("account"), request("batch")],
                                      sort_keys=False), "  ")
        return prefix + "steps:\n" + prior + (
            "  - id: consume\n    do:\n      request:\n        method: POST\n"
            "        path: [records]\n        body:\n          composed:\n") + indent(body, "            ") + (
            "    expect:\n      response:\n        - check: success\n")
    earlier = {"query": "first_page", "comparison": "read_before", "collection": "create",
               "dictionary": "create", "member": "locate", "stop": "create"}.get(name)
    prior = indent(yaml.safe_dump([request(earlier)], sort_keys=False), "  ") if earlier else ""
    if name == "results":
        return prefix + "steps:\n" + indent(yaml.safe_dump([request("create_request")],
                                                           sort_keys=False), "  ") + body
    if name in {"comparison", "numeric_length", "status_equals", "status_in"}:
        return prefix + "steps:\n" + prior + (
            "  - id: inspect\n    do:\n      request:\n        method: GET\n"
            "        path: [records]\n    expect:\n      response:\n") + indent(body, "        ")
    if name in {"dictionary", "member"}:
        return prefix + "steps:\n" + prior + (
            "  - id: consume\n    do:\n      request:\n        method: POST\n"
            "        path: [records]\n        body:\n          selected:\n") + indent(body, "            ") + (
            "    expect:\n      response:\n        - check: success\n")
    return prefix + "steps:\n" + prior + indent(body, "  ")


def write_context(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "documented.yaml"
    path.write_text(render_context(name, body), encoding="utf-8")
    if name in {"include", "mapped_include"}:
        child = directory / "child.yaml"
        if name == "include":
            child_data = {"schema_version": 1, "scenario": "demo.create_record", "users": ["operator"],
                "parameters": {"record_name": "Default"}, "steps": [{"id": "create_request",
                    "do": {"request": {"method": "POST", "path": ["records"],
                        "body": {"name": {"from_parameter": "record_name"}}}},
                    "expect": {"response": [{"check": "success"}]}}]}
            child.write_text(yaml.safe_dump(child_data, sort_keys=False), encoding="utf-8")
            scenario_id = child_data["scenario"]
        else:
            child.write_bytes((ROOT / "examples/documents/scenarios/shared/access_document.yaml").read_bytes())
            scenario_id = "documents.shared_access"
        assert load_scenario(child).id == scenario_id
        path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
            "scenarios": {scenario_id: {"path": child.name,
                "sha256": hashlib.sha256(child.read_bytes()).hexdigest()}}}), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", CONTEXTS)
def test_every_actual_contract_fence_loads_in_its_explicit_context(tmp_path, name):
    body = inventory(DOCUMENT.read_text(encoding="utf-8"))[name]
    path = write_context(tmp_path, name, body)
    scenario = load_scenario(path)
    assert scenario.steps
    if name in {"include", "mapped_include"}:
        assert scenario.source_lookup
    if name == "results":
        assert set(scenario.results) == {"record_id", "record_name"}


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "new", "extra_info", "unknown_signature", "unclosed"])
def test_fence_inventory_cannot_silently_omit_declarations(mutation):
    text = DOCUMENT.read_text(encoding="utf-8")
    body = inventory(text)["query"]
    changed = {
        "missing": text.replace("```yaml\n" + body + "```", ""),
        "duplicate": text + "\n```yaml\n" + body + "```\n",
        "new": text + "\n~~~YAML\nscenario: demo.unreviewed\n~~~\n",
        "extra_info": text + '\n```yaml title="unreviewed"\nscenario: demo.unreviewed\n```\n',
        "unknown_signature": text.replace("- id: next_page\n", "- id: unreviewed\n", 1),
        "unclosed": text + "\n```yaml\n- id: unfinished\n",
    }[mutation]
    with pytest.raises(AssertionError):
        inventory(changed)


@pytest.mark.parametrize("opening,closing", [
    ("   ~~~~YML", "   ~~~~"), ("````yaml", "`````"),
    ('```yaml title="query"', "```"),
])
def test_alternate_valid_fences_are_inventoried(opening, closing):
    text = DOCUMENT.read_text(encoding="utf-8")
    body = inventory(text)["query"]
    changed = text.replace("```yaml\n" + body + "```", opening + "\n" + body + closing, 1)
    assert inventory(changed) == inventory(text)


@pytest.mark.parametrize("name,before,after", [
    ("query", "from_step: first_page", "from_step: absent_page"),
    ("status_equals", "value: 201", "value: true"),
    ("dictionary", "key: id", "key: []"),
    ("include", "demo.create_record", "demo.missing_child"),
    ("results", "from_step: create_request", "from_step: missing_request"),
    ("ui", "check: objects_matching_count", "check: unsupported_check"),
    ("status_equals", "value: 201", "value: 201\n  value: 202"),
    ("run_parameters", "from_run: unique", "from_run: unsupported"),
    ("time_parameters", "days: 7", "days: true"),
    ("response_concat", "from_step: account", "from_step: missing_account"),
])
def test_invalid_actual_fragment_is_not_replaced_with_a_valid_copy(tmp_path, name, before, after):
    body = inventory(DOCUMENT.read_text(encoding="utf-8"))[name]
    assert before in body
    assert load_scenario(write_context(tmp_path / "valid", name, body)).steps
    with pytest.raises(DeclarationError):
        load_scenario(write_context(tmp_path / "invalid", name, body.replace(before, after)))


def test_documented_include_uses_a_checked_pin(tmp_path):
    body = inventory(DOCUMENT.read_text(encoding="utf-8"))["mapped_include"]
    path = write_context(tmp_path, "mapped_include", body)
    assert load_scenario(path).steps
    child = tmp_path / "child.yaml"
    child.write_bytes(child.read_bytes() + b"\n# changed after review\n")
    with pytest.raises(DeclarationError, match="fingerprint"):
        load_scenario(path)


@dataclass(frozen=True)
class Consumer:
    node: str
    projections: str
    via: str | None = None


EXAMPLES = {
    "examples/documents/scenarios/owner_peer.yaml": Consumer("tests/test_documents_users_sessions.py::test_owner_reads_and_distinct_same_role_peer_is_denied", "backend, contract, API e2e"),
    "examples/documents/scenarios/permission_sessions.yaml": Consumer("tests/test_documents_users_sessions.py::test_permission_change_old_session_then_reauthenticate_same_account", "backend, contract, API e2e"),
    "examples/documents/scenarios/shared/create_document.yaml": Consumer("tests/test_documents_users_sessions.py::test_owner_reads_and_distinct_same_role_peer_is_denied", "backend, contract, API e2e", "examples/documents/scenarios/owner_peer.yaml"),
    "examples/documents/scenarios/mapped_peer_access.yaml": Consumer("tests/test_anonymous_documents.py::test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant", "backend, contract, API e2e"),
    "examples/documents/scenarios/mapped_anonymous_access.yaml": Consumer("tests/test_anonymous_documents.py::test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant", "backend, contract, API e2e"),
    "examples/documents/scenarios/shared/access_document.yaml": Consumer("tests/test_anonymous_documents.py::test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant", "backend, contract, API e2e", "examples/documents/scenarios/mapped_peer_access.yaml"),
    "examples/documents/scenarios/filter_and_next_page.yaml": Consumer("tests/test_query_documents.py::test_approved_five_step_example_follows_observed_cursor", "backend, contract, API e2e"),
    "examples/minimal/idempotent_create.yaml": Consumer("tests/demo/test_demo_headers.py::test_approved_records_retry_example_uses_real_http_and_independent_target_capture", "backend, contract, API e2e; real HTTP"),
    "examples/minimal/rejected_update_preserves_content.yaml": Consumer("tests/test_field_comparison_consumers.py::test_complete_read_before_and_after_real_refusal", "backend, contract, API e2e"),
    "examples/documents/scenarios/rejected_update_preserves_content.yaml": Consumer("tests/test_field_comparison_consumers.py::test_complete_read_before_and_after_real_refusal", "backend, contract, API e2e"),
    "examples/documents/scenarios/check_page_limits.yaml": Consumer("tests/test_numeric_check_consumers.py::test_real_isolated_consumers_follow_two_pages_without_mutating_evidence", "backend, contract, API e2e"),
    "examples/minimal/check_page_limits.yaml": Consumer("tests/test_numeric_check_consumers.py::test_real_isolated_consumers_follow_two_pages_without_mutating_evidence", "backend, contract, API e2e"),
    "examples/documents/scenarios/run_unique_create_locate_read.yaml": Consumer("tests/test_run_value_consumers.py::test_new_runs_on_same_target_locate_the_new_object_not_old_residue", "backend, contract, API e2e"),
    "examples/minimal/run_unique_create_locate_read.yaml": Consumer("tests/test_run_value_consumers.py::test_new_runs_on_same_target_locate_the_new_object_not_old_residue", "backend, contract, API e2e"),
    "examples/minimal/create_expiring_record.yaml": Consumer("tests/test_run_time_consumers.py::test_public_expiration_example_creates_and_reads_real_record", "backend, contract, API e2e"),
    "examples/documents/scenarios/query_recent_documents.yaml": Consumer("tests/test_run_time_consumers.py::test_public_recent_query_example_sends_frozen_window", "backend, contract, API e2e"),
    "examples/documents/scenarios/http_status_create_delete.yaml": Consumer("tests/test_http_status_consumers.py::test_documents_complete_example_creates_201_and_deletes_empty_204", "backend, contract"),
    "examples/minimal/create_locate_update_read.yaml": Consumer("tests/test_member_reference_consumers.py::test_independent_consumers_use_real_selected_identifier", "backend, contract, API e2e"),
    "examples/minimal/dictionary_record_reference.yaml": Consumer("tests/test_member_reference_consumers.py::test_independent_consumers_use_real_selected_identifier", "backend, contract, API e2e"),
    "scenarios/demo_include_items.yaml": Consumer("tests/demo/test_demo_include.py::test_api_include_reuses_actual_response_and_matches_flat_runtime", "backend, contract; real HTTP"),
    "scenarios/demo_include_items_ui.yaml": Consumer("tests/demo/test_demo_include.py::test_ui_include_reuses_one_context_and_matches_flat_runtime", "frontend, live UI e2e; Chromium"),
    "examples/documents/scenarios/continue_after_failure.yaml": Consumer("tests/test_documents_failure_continuation.py::test_documents_collect_checks_and_really_delete", "backend, contract, API e2e"),
}
PINS = {"scenarios/demo_include_items.includes.json", "scenarios/demo_include_items_ui.includes.json"}


def linked_examples(text):
    paths = re.findall(r"\]\(([^)]+\.(?:yaml|json))\)", text)
    assert len(paths) == len(set(paths)), "Repeated linked example needs explicit inventory"
    assert set(paths) == set(EXAMPLES) | PINS, "Linked examples and consumer inventory differ"
    for relative in paths:
        assert (ROOT / relative).is_file(), f"Missing linked example: {relative}"
    return paths


def assert_pin(parent, child=None):
    manifest = json.loads(parent.with_suffix(".includes.json").read_text(encoding="utf-8"))
    targets = []
    for entry in manifest["scenarios"].values():
        target = (parent.parent / entry["path"]).resolve()
        assert target.is_file()
        assert entry["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        targets.append(target)
    if child is not None:
        assert child.resolve() in targets


def test_all_linked_examples_exist_load_and_have_exact_indirect_pins():
    assert len(linked_examples(DOCUMENT.read_text(encoding="utf-8"))) == 24
    for relative, consumer in EXAMPLES.items():
        path = ROOT / relative
        assert load_scenario(path).steps
        if consumer.via:
            assert_pin(ROOT / consumer.via, path)
    for relative in PINS:
        assert_pin((ROOT / relative).with_suffix("").with_suffix(".yaml"))


@pytest.mark.parametrize("mutation", ["missing", "extra", "broken"])
def test_link_inventory_rejects_unaccounted_examples(mutation):
    text = DOCUMENT.read_text(encoding="utf-8")
    path = "examples/minimal/idempotent_create.yaml"
    changed = {
        "missing": text.replace(f"]({path})", "](removed)"),
        "extra": text + "\n[Unreviewed](examples/minimal/unreviewed.yaml)\n",
        "broken": text.replace(path, "examples/minimal/missing.yaml"),
    }[mutation]
    with pytest.raises(AssertionError):
        linked_examples(changed)


def test_consumer_inventory_names_real_functions_and_collected_nodes():
    nodes = {consumer.node for consumer in EXAMPLES.values()}
    for node in nodes:
        relative, function = node.split("::")
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        assert any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function
                   for item in tree.body), node
    # The dev-only job intentionally excludes Demo dependencies. Verify its
    # available owners here; full-suite CI collects AND executes every owner.
    demo_present = all(importlib.util.find_spec(name) is not None
                       for name in ("httpx", "fastapi", "uvicorn", "playwright"))
    expected = {node for node in nodes if demo_present or not node.startswith("tests/demo/")}
    result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
        "-o", "addopts=", "-p", "no:cacheprovider", *sorted(expected)], cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True,
        text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    collected = {line.split("[", 1)[0] for line in result.stdout.splitlines()
                 if line.startswith("tests/") and "::" in line}
    assert collected == expected


def test_full_suite_ci_includes_optional_real_consumers_without_selection_filter():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    commands = [step.get("run", "") for step in workflow["jobs"]["full-suite"]["steps"]]
    assert any('pip install -e ".[dev,demo]"' in command for command in commands)
    assert any("playwright install --with-deps chromium" in command for command in commands)
    assert "pytest -q" in commands
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
