"""Every compact boundary is an actual loader rejection in a valid context."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

from refracto.declaration.loader import DeclarationError, load_scenario


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/boundaries.md"


@dataclass(frozen=True)
class Boundary:
    context: str
    error: str
    file: str
    function: str

    @property
    def node(self):
        return f"tests/{self.file}.py::{self.function}"


CASES = {
    "T01": Boundary("top", "users must be a list of distinct non-empty literal names", "test_users_sessions_core", "test_users_required_actor_rejected_and_no_role_metadata"),
    "T02": Boundary("top", "every step in a multi-user Scenario must declare user", "test_users_sessions_core", "test_multiuser_requires_user_on_every_step"),
    "S01": Boundary("leaf", "on_failure must be the literal string stop; omit it to continue", "test_failure_continuation", "test_only_explicit_literal_stop_is_allowed"),
    "S02": Boundary("leaf", "on_failure must be the literal string stop; omit it to continue", "test_failure_continuation", "test_only_explicit_literal_stop_is_allowed"),
    "S03": Boundary("leaf", "session must be the literal string new; omit it to reuse", "test_users_sessions_core", "test_only_explicit_new_session"),
    "S04": Boundary("include", "include step: unknown field(s) ['on_failure']", "test_failure_continuation", "test_include_call_cannot_override_policy"),
    "S05": Boundary("mapped", "with_users must map every declared child user exactly once", "test_anonymous_users_inclusion", "test_malformed_or_colliding_user_mappings_rejected"),
    "S06": Boundary("mapped", "distinct child users must map to distinct parent participants", "test_anonymous_users_inclusion", "test_malformed_or_colliding_user_mappings_rejected"),
    "S07": Boundary("anonymous_child", "an anonymous child participant must remain anonymous", "test_anonymous_users_inclusion", "test_explicit_child_anonymous_cannot_be_upgraded_in_full_mapping"),
    "D01": Boundary("request", "query values must be strings, integers, booleans, or finite floats", "test_query_parameters", "test_loader_rejects_invalid_query"),
    "D02": Boundary("request", "query values must be strings, integers, booleans, or finite floats", "test_query_parameters", "test_loader_rejects_invalid_query"),
    "D03": Boundary("request", "query keys must be nonempty literal strings", "test_query_parameters", "test_loader_rejects_invalid_query"),
    "D04": Boundary("request", "credential and transport header declarations are forbidden", "test_business_headers", "test_credentials_transport_and_reserved_prefixes_rejected"),
    "D05": Boundary("request", "duplicate case-insensitive header name", "test_business_headers", "test_invalid_header_maps_are_rejected_without_values"),
    "D06": Boundary("request", "header value must be a string of visible ASCII without surrounding whitespace", "test_business_headers", "test_invalid_header_maps_are_rejected_without_values"),
    "E01": Boundary("checks", "status_equals.value must be a literal integer from 100 through 599", "test_http_status_assertions", "test_status_equals_rejects_nonliteral_or_invalid_values"),
    "E02": Boundary("checks", "status_in.values must be a nonempty list of distinct literal integers from 100 through 599", "test_http_status_assertions", "test_status_in_rejects_invalid_sets"),
    "E03": Boundary("checks", "at most one HTTP status constraint is allowed per step", "test_http_status_assertions", "test_missing_extra_and_duplicate_constraints_rejected"),
    "E04": Boundary("checks", "response.field_equals: missing required param ['value']", "test_response_field_comparison", "test_comparison_requires_both_parameters"),
    "E05": Boundary("checks", "response.field_equals.value requires finite JSON-like data", "test_response_field_comparison", "test_invalid_declared_data_rejected"),
    "E06": Boundary("checks", "field_absent conflicts with a response presence constraint", "test_response_field_comparison", "test_duplicate_and_presence_conflicts_rejected"),
    "E07": Boundary("checks", "response numeric comparison operator is unsupported", "test_response_numeric_length", "test_invalid_shape_field_and_operator_rejected"),
    "E08": Boundary("checks", "field_compare value must be a finite number", "test_response_numeric_length", "test_invalid_literals_and_parameter_defaults_rejected"),
    "E09": Boundary("checks", "collection_length value must be a non-negative integer", "test_response_numeric_length", "test_invalid_literals_and_parameter_defaults_rejected"),
    "R01": Boundary("reference", "response member reference requires either key or matching with member_field", "test_response_member_references", "test_malformed_shapes_and_sources_are_rejected"),
    "R02": Boundary("reference", "response member reference requires either key or matching with member_field", "test_response_member_references", "test_malformed_shapes_and_sources_are_rejected"),
    "R03": Boundary("reference", "response reference key must be a non-empty string", "test_response_member_references", "test_literal_nonblank_selector_names_required"),
}

CAPABILITIES = {
    "status": ("E01", "E02", "E03"),
    "continuation": ("S01", "S02", "S04"),
    "users_sessions": ("T01", "T02", "S03"),
    "rejection_evidence": ("E01", "E03", "E04"),
    "query": ("D01", "D02", "D03"),
    "anonymous_mapping": ("S05", "S06", "S07"),
    "headers": ("D04", "D05", "D06"),
    "complete_comparison": ("E04", "E05", "E06"),
    "member_references": ("R01", "R02", "R03"),
    "numeric_length": ("E07", "E08", "E09"),
}

ROW = re.compile(
    r"^\| (?P<id>[A-Z][0-9]{2}) \| `(?P<fragment>[^`]+)` \| "
    r"(?P<reason>[^|]+) \| \[(?P<function>test_[a-z0-9_]+)\]"
    r"\(\.\./(?P<file>tests/test_[a-z0-9_]+\.py)\) \|$"
)
SECTIONS = {
    "top": "Top level",
    "leaf": "Step, including an include call",
    "include": "Step, including an include call",
    "mapped": "Step, including an include call",
    "anonymous_child": "Step, including an include call",
    "request": "Do: request fields",
    "checks": "Expect: response checks",
    "reference": "Prior-response references",
}


def read_rows(text):
    rows = {}
    section, seen_sections = None, set()
    for line in text.splitlines():
        line = line.lstrip()
        if line.startswith("## "):
            section = line[3:]
            assert section in SECTIONS.values() and section not in seen_sections
            seen_sections.add(section)
        if not line.startswith("|"):
            continue
        if line in {
            "| ID | Cannot write | Rejection reason | Existing test |",
            "| --- | --- | --- | --- |",
        }:
            continue
        match = ROW.fullmatch(line)
        assert match, f"Unrecognized boundary row: {line}"
        row = match.groupdict()
        identity = row["id"]
        assert identity not in rows, f"Duplicate boundary: {identity}"
        assert identity in CASES, f"Unknown boundary: {identity}"
        assert section == SECTIONS[CASES[identity].context], identity
        rows[identity] = row
    assert seen_sections == set(SECTIONS.values())
    assert set(rows) == set(CASES), "Boundary IDs and executable contexts differ"
    for identity, row in rows.items():
        case = CASES[identity]
        assert f"{row['file']}::{row['function']}" == case.node, identity
        assert row["reason"].strip(), identity
        assert "..." not in row["fragment"], identity
    return rows


def request(identity="read", user=None):
    step = {"id": identity, "do": {"request": {"method": "GET", "path": ["records"]}},
            "expect": {"response": [{"check": "success"}]}}
    if user is not None:
        step["user"] = user
    return step


def context(kind):
    declaration = {"schema_version": 1, "scenario": "demo.boundary_review", "users": ["owner"],
                   "parameters": {"policy": "stop", "key": "id"}, "steps": [request()]}
    child = None
    if kind == "reference":
        declaration["steps"] = [request("source"), request("consume")]
    elif kind in {"include", "mapped", "anonymous_child"}:
        anonymous = kind == "anonymous_child"
        child_users = ["creator", "anonymous" if anonymous else "reader"]
        child = {"schema_version": 1, "scenario": "demo.boundary_child", "users": child_users,
                 "steps": [request("create", "creator"), request("read", child_users[1])]}
        declaration["users"] = ["owner", "peer", "anonymous"]
        declaration["steps"] = [{"id": "setup", "do": {"include": child["scenario"]},
            "with_users": {"creator": "owner", child_users[1]: "anonymous"}}]
    return declaration, child


def write_bundle(directory, declaration, child):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "scenario.yaml"
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    if child is not None:
        source = directory / "child.yaml"
        source.write_text(yaml.safe_dump(child, sort_keys=False), encoding="utf-8")
        path.with_suffix(".includes.json").write_text(json.dumps({"manifest_version": 1,
            "scenarios": {child["scenario"]: {"path": source.name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}}), encoding="utf-8")
    return path


def insert_fragment(declaration, fragment, kind):
    actual = yaml.safe_load(fragment)
    step = declaration["steps"][-1]
    if kind == "top":
        declaration.update(actual)
    elif kind in {"leaf", "include", "mapped", "anonymous_child"}:
        step.update(actual)
    elif kind == "request":
        step["do"]["request"].update(actual)
    elif kind == "checks":
        assert isinstance(actual, list)
        step["expect"]["response"] = actual
    elif kind == "reference":
        step["do"]["request"]["body"] = {"selected": actual}
    else:
        raise AssertionError(f"Unknown context: {kind}")


def assert_boundary(identity, fragment, directory):
    case = CASES[identity]
    original, child = context(case.context)
    # No undeclared parameter, invalid pin or assertion-free wrapper may supply
    # the rejection attributed to the documented fragment.
    assert load_scenario(write_bundle(directory / "valid", original, child)).steps
    invalid = deepcopy(original)
    insert_fragment(invalid, fragment, case.context)
    with pytest.raises(DeclarationError) as error:
        load_scenario(write_bundle(directory / "invalid", invalid, child))
    assert str(error.value) == case.error, f"Unrelated rejection for {identity}"


@pytest.mark.parametrize("identity", CASES)
def test_documented_fragment_rejected_in_valid_context(tmp_path, identity):
    row = read_rows(DOCUMENT.read_text(encoding="utf-8"))[identity]
    assert_boundary(identity, row["fragment"], tmp_path)


def test_ten_capabilities_have_three_real_representative_boundaries():
    rows = read_rows(DOCUMENT.read_text(encoding="utf-8"))
    assert len(rows) == 27 <= 30
    assert len(CAPABILITIES) == 10
    assert all(len(set(entries)) == 3 for entries in CAPABILITIES.values())
    assert set().union(*map(set, CAPABILITIES.values())) == set(rows)
    assert CAPABILITIES["rejection_evidence"] == ("E01", "E03", "E04")


def test_cited_functions_are_real_collected_pytest_nodes():
    rows = read_rows(DOCUMENT.read_text(encoding="utf-8"))
    expected = {f"{row['file']}::{row['function']}" for row in rows.values()}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=",
         "-p", "no:cacheprovider", *sorted(expected)], cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True,
        timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    collected = {line.split("[", 1)[0] for line in completed.stdout.splitlines()
                 if line.startswith("tests/") and "::" in line}
    assert collected == expected


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "malformed", "citation", "section"])
def test_sentinel_detects_unmapped_or_mislinked_rows(mutation):
    original = DOCUMENT.read_text(encoding="utf-8")
    line = next(line for line in original.splitlines() if line.startswith("| E01 |"))
    changed = {
        "missing": original.replace(line + "\n", ""),
        "duplicate": original + "\n" + line + "\n",
        "unknown": original.replace("| E01 |", "| E99 |"),
        "malformed": original.replace(line, line.replace('`[{check:', '[{check:', 1)),
        "citation": original.replace(line, line.replace(
            "test_status_equals_rejects_nonliteral_or_invalid_values", "test_status_in_rejects_invalid_sets")),
        "section": original.replace("## Top level", "## Expect: response checks"),
    }[mutation]
    with pytest.raises(AssertionError):
        read_rows(changed)


@pytest.mark.parametrize("extra", [
    "|E99|`[{check: not_registered}]`|unreviewed|[test_missing](../tests/test_missing.py)|",
    "  \t|E99|`[{check: not_registered}]`|unreviewed|[test_missing](../tests/test_missing.py)|",
    "| ID | unreviewed | hidden | data |",
    "| --- | unreviewed | hidden | data |",
])
def test_sentinel_never_ignores_compact_indented_or_header_prefixed_rows(extra):
    with pytest.raises(AssertionError, match="Unrecognized boundary row"):
        read_rows(DOCUMENT.read_text(encoding="utf-8") + "\n" + extra + "\n")


def test_sentinel_rejects_a_documented_fragment_that_now_loads(tmp_path):
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        assert_boundary("E01", "[{check: status_equals, value: 201}]", tmp_path)


def test_sentinel_rejects_an_unrelated_declaration_error(tmp_path):
    with pytest.raises(AssertionError, match="Unrelated rejection"):
        assert_boundary("E01", "[{check: field_equals, field: missing_value}]", tmp_path)


def test_sentinel_never_counts_an_unexpected_exception_as_rejection(tmp_path, monkeypatch):
    real_loader = load_scenario

    def broken_loader(path):
        if path.parent.name == "invalid":
            raise RuntimeError("synthetic loader defect")
        return real_loader(path)

    monkeypatch.setattr(sys.modules[__name__], "load_scenario", broken_loader)
    with pytest.raises(RuntimeError, match="synthetic loader defect"):
        assert_boundary("E01", read_rows(DOCUMENT.read_text())["E01"]["fragment"], tmp_path)
