"""Executable documentation and the approved five-step pagination obligations."""
from pathlib import Path
import re

import pytest
import yaml

from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import load_scenario
from refracto.ports import NormalizedResponse
from refracto.projection.backend import _eval_response


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("document", ["SCENARIO.md", "docs/tasks/response-numeric-length-checks.md"])
def test_documented_numeric_and_length_fragment_loads_and_checks_actual_values(tmp_path, document):
    blocks = re.findall(r"```yaml\n(.*?)```", (ROOT / document).read_text(), re.S)
    fragments = [yaml.safe_load(block) for block in blocks
                 if "check: collection_length" in block and "check: field_compare" in block]
    assert fragments
    for index, fragment in enumerate(fragments):
        assert isinstance(fragment, list)
        declaration = {
            "schema_version": 1, "scenario": "records.documented_page_limits", "users": [],
            "parameters": {"page_size": 1},
            "steps": [{"id": "page", "do": {"request": {"method": "GET", "path": ["records"]}},
                       "expect": {"response": fragment}}],
        }
        path = tmp_path / f"numeric-fragment-{index}.yaml"
        path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
        scenario = load_scenario(path)
        prepared, bound = prepare_step(scenario.steps[0], scenario, {})
        assert bound == {}
        assert [(check.check, check.params["field"], check.params["op"], check.params["value"])
                for check in prepared.expect.response] == [
            ("field_compare", "returned", ">=", 1), ("field_compare", "returned", "<=", 1),
            ("collection_length", "documents", ">=", 1), ("collection_length", "documents", "<=", 1)]
        actual = NormalizedResponse(True, {"returned": 1, "documents": [{"id": "observed"}]}, 200, None)
        assert all(_eval_response(check, actual).ok for check in prepared.expect.response)
        actual.fields["documents"].append({"id": "extra"})
        assert [_eval_response(check, actual).ok for check in prepared.expect.response] == [True, True, True, False]


@pytest.mark.parametrize("kind,relative,user,identifier,first,second,memo", [
    ("documents", "examples/documents/scenarios/check_page_limits.yaml", "editor", "document_id",
     "Getting started", "Advanced usage", "Internal memo"),
    ("records", "examples/minimal/check_page_limits.yaml", "creator", "id",
     "First record", "Second record", "Unrelated memo"),
])
def test_published_page_limit_examples_preserve_complete_visible_setup_and_obligations(
        kind, relative, user, identifier, first, second, memo):
    path = ROOT / relative
    raw = yaml.safe_load(path.read_text())
    assert raw["schema_version"] == 1 and raw["scenario"] == f"{kind}.check_page_limits"
    assert raw["users"] == [user]
    assert raw["parameters"] == {"category": "guide", "page_size": 1,
                                 "first_title": first, "second_title": second}
    assert [step["id"] for step in raw["steps"]] == [
        "create_first", "create_other_category", "create_second", "first_page", "next_page"]
    assert [step.get("on_failure") for step in raw["steps"]] == ["stop"] * 4 + [None]
    create_first, create_memo, create_second, first_page, next_page = raw["steps"]
    for step, title in [(create_first, "first_title"), (create_second, "second_title")]:
        assert step["do"] == {"request": {"method": "POST", "path": [kind], "body": {
            "title": {"from_parameter": title}, "category": {"from_parameter": "category"}}}}
        assert step["expect"]["response"] == [
            {"check": "status_equals", "value": 201}, {"check": "success"},
            {"check": "has", "field": identifier}]
    assert create_memo["do"] == {"request": {"method": "POST", "path": [kind],
                                                "body": {"title": memo, "category": "memo"}}}
    assert create_memo["expect"]["response"] == [
        {"check": "status_equals", "value": 201}, {"check": "success"},
        {"check": "field_equals", "field": "category", "value": "memo"}]
    for page, source, title in [(first_page, "create_first", "first_title"),
                                (next_page, "create_second", "second_title")]:
        cursor = 0 if source == "create_first" else {"from_step": "first_page", "response_field": "next_cursor"}
        assert page["do"] == {"request": {"method": "GET",
            "path": ["documents", "search"] if kind == "documents" else ["records"],
            "query": {"category": {"from_parameter": "category"},
                      "limit": {"from_parameter": "page_size"}, "cursor": cursor}}}
        assert page["expect"]["response"] == [
            {"check": "status_equals", "value": 200}, {"check": "success"},
            {"check": "field_compare", "field": "returned", "op": ">=", "value": 1},
            {"check": "field_compare", "field": "returned", "op": "<=", "value": {"from_parameter": "page_size"}},
            {"check": "collection_length", "field": kind, "op": ">=", "value": 1},
            {"check": "collection_length", "field": kind, "op": "<=", "value": {"from_parameter": "page_size"}},
            {"check": "collection_matching_count", "field": kind, "count": 1, "matching": {
                identifier: {"from_step": source, "response_field": identifier},
                "title": {"from_parameter": title}, "category": {"from_parameter": "category"}}},
            {"check": "field_not_equals" if source == "create_first" else "field_equals",
             "field": "next_cursor", "value": None},
        ]
    assert [step.id for step in load_scenario(path).steps] == [step["id"] for step in raw["steps"]]
