"""Frozen review sources: paired meaning, exact changes, and byte pins.

The flat YAML files are separately authored inputs. These tests do not create
them by expansion and do not read the human answer key to determine correctness.
"""
from copy import deepcopy
from dataclasses import fields
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

import pytest
import yaml

from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import DeclarationError, load_scenario
from refracto.declaration.model import Expect, Step
from refracto.ports import NormalizedResponse


ROOT = Path(__file__).resolve().parents[1] / "docs/review-exercise"
VERSIONS = ("baseline", "case-01", "case-02", "case-03")
FORMS = ("included", "flat")
ROW_CHECK = {"check": "span_attr", "span": "item.create", "attr": "row_count",
             "op": "==", "value": 3}


def source(version, filename):
    return yaml.safe_load((ROOT / version / filename).read_text(encoding="utf-8"))


def first_step(version):
    return "persist" if version == "case-01" else "create"


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("filename", ("included.yaml", "child.yaml", "flat.yaml"))
def test_every_review_source_loads(version, filename):
    scenario = load_scenario(ROOT / version / filename)
    assert scenario.users == ["user"]
    assert len(scenario.steps) == (1 if filename == "child.yaml" else 3)
    assert all(step.action == "request" for step in scenario.steps)


@pytest.mark.parametrize("version", VERSIONS)
def test_each_sidecar_pins_exact_child_bytes(version):
    child = ROOT / version / "child.yaml"
    sidecar = ROOT / version / "included.includes.json"
    assert json.loads(sidecar.read_text(encoding="utf-8")) == {
        "manifest_version": 1,
        "scenarios": {"review.create_item": {
            "path": "child.yaml", "sha256": hashlib.sha256(child.read_bytes()).hexdigest()}}}
    scenario = load_scenario(ROOT / version / "included.yaml")
    child_scenario = load_scenario(child)
    assert list(child_scenario.results) == ["record_id"]
    assert child_scenario.results["record_id"].from_step == first_step(version)
    assert child_scenario.results["record_id"].response_field == "itemId"
    assert scenario.source_lookup[f"setup/{first_step(version)}"]["sha256"] == (
        hashlib.sha256(child.read_bytes()).hexdigest())


def concrete_plan(version, form, returned_id):
    """Materialize only at the existing binding seam, using explicit source IDs.

    Include expansion loads the candidate; it never produces the independently
    authored flat source. Every request body and every assertion is compared.
    Binding placeholders and raw template paths are compilation metadata; their
    resolved values and concrete paths are included in the comparison instead.
    """
    scenario = load_scenario(ROOT / version / f"{form}.yaml")
    local_first = first_step(version)
    first_id = f"setup/{local_first}" if form == "included" else local_first
    id_map = {first_id: "create", "update": "update", "read": "read"}
    assert [step.id for step in scenario.steps] == list(id_map)
    # Fail closed if the public model adds a new field this comparison ignores.
    assert {f.name for f in fields(Step)} == {
        "id", "request", "expect", "bind", "poll", "action", "target",
        "value", "duration", "request_asserted", "on_failure", "user", "session", "object_id"}
    assert {f.name for f in fields(Expect)} == {"frontend", "response", "backend_state"}
    prior, result = {}, []
    for step in scenario.steps:
        prepared, _ = prepare_step(step, scenario, prior)
        request = prepared.request
        result.append({
            "id": id_map[step.id], "action": prepared.action,
            "target": prepared.target, "value": prepared.value, "object_id": prepared.object_id,
            "duration": prepared.duration, "poll": prepared.poll,
            "request_asserted": prepared.request_asserted,
            "on_failure": prepared.on_failure,
            "user": prepared.user, "session": prepared.session,
            "request": {"method": request.method, "path": request.path, "body": request.body},
            "expect": {point: [{"check": a.check, **a.params}
                               for a in getattr(prepared.expect, point)]
                       for point in ("frontend", "response", "backend_state")},
        })
        if step.id == first_id:
            prior[first_id] = NormalizedResponse(
                True, {"itemId": returned_id, "name": request.body["name"]}, 200, None)
    return result


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("returned_id", (41, 907))
def test_materialized_pair_matches_all_inputs_and_assertions(version, returned_id):
    included = concrete_plan(version, "included", returned_id)
    flat = concrete_plan(version, "flat", returned_id)
    # JSON serialization preserves distinctions such as bool versus integer.
    assert json.dumps(included, sort_keys=True) == json.dumps(flat, sort_keys=True)
    created_name = "review-final" if version == "case-02" else "review-draft"
    assert [step["request"] for step in included] == [
        {"method": "POST", "path": "items", "body": {"name": created_name, "rows": [1, 2, 3]}},
        {"method": "PUT", "path": f"items/{returned_id}", "body": {"name": "review-final"}},
        {"method": "GET", "path": "items", "body": None},
    ]
    assert [step["expect"] for step in included] == [
        {"frontend": [], "response": [
            {"check": "success"}, {"check": "has", "field": "itemId"},
            {"check": "field_equals", "field": "name", "value": created_name}],
         "backend_state": [{"check": "span_exists", "span": "item.create"}] + (
             [] if version == "case-03" else [ROW_CHECK])},
        {"frontend": [], "response": [
            {"check": "success"}, {"check": "field_equals", "field": "itemId", "value": returned_id}],
         "backend_state": [{"check": "span_exists", "span": "item.update"}]},
        {"frontend": [], "response": [
            {"check": "success"},
            {"check": "collection_matching_count", "field": "items",
             "matching": {"id": returned_id, "name": "review-final"}, "count": 1}],
         "backend_state": []},
    ]


def test_case_01_changes_only_internal_step_and_references():
    assert (ROOT / "case-01/included.yaml").read_bytes() == (ROOT / "baseline/included.yaml").read_bytes()
    expected_child = deepcopy(source("baseline", "child.yaml"))
    expected_child["steps"][0]["id"] = "persist"
    expected_child["results"]["record_id"]["from_step"] = "persist"
    assert source("case-01", "child.yaml") == expected_child
    baseline_flat = (ROOT / "baseline/flat.yaml").read_text(encoding="utf-8")
    expected_flat = baseline_flat.replace("id: create", "id: persist").replace(
        "from_step: create", "from_step: persist")
    assert (ROOT / "case-01/flat.yaml").read_text(encoding="utf-8") == expected_flat
    assert (ROOT / "case-01/included.includes.json").read_bytes() != (
        ROOT / "baseline/included.includes.json").read_bytes()
    assert concrete_plan("case-01", "included", 41) == concrete_plan("baseline", "included", 41)


def test_case_02_changes_only_creation_argument_and_equivalent_flat_assertion():
    expected_parent = deepcopy(source("baseline", "included.yaml"))
    expected_parent["steps"][0]["with"]["item_name"] = {"from_parameter": "final_name"}
    assert source("case-02", "included.yaml") == expected_parent
    for filename in ("child.yaml", "included.includes.json"):
        assert (ROOT / "case-02" / filename).read_bytes() == (ROOT / "baseline" / filename).read_bytes()
    expected_flat = deepcopy(source("baseline", "flat.yaml"))
    create = expected_flat["steps"][0]
    create["do"]["request"]["body"]["name"] = {"from_parameter": "final_name"}
    create["expect"]["response"][2]["value"] = {"from_parameter": "final_name"}
    assert source("case-02", "flat.yaml") == expected_flat
    assert concrete_plan("case-02", "included", 41) != concrete_plan("baseline", "included", 41)


def test_case_03_removes_only_creation_row_count_assertion():
    assert (ROOT / "case-03/included.yaml").read_bytes() == (ROOT / "baseline/included.yaml").read_bytes()
    for filename in ("child.yaml", "flat.yaml"):
        expected = deepcopy(source("baseline", filename))
        assert expected["steps"][0]["expect"]["backend_state"].pop() == ROW_CHECK
        assert source("case-03", filename) == expected
    assert (ROOT / "case-03/included.includes.json").read_bytes() != (
        ROOT / "baseline/included.includes.json").read_bytes()


def test_changed_child_with_stale_pin_is_rejected(tmp_path):
    for filename in ("included.yaml", "included.includes.json"):
        shutil.copyfile(ROOT / "baseline" / filename, tmp_path / filename)
    shutil.copyfile(ROOT / "case-01/child.yaml", tmp_path / "child.yaml")
    with pytest.raises(DeclarationError, match="fingerprint|sha256|SHA-256"):
        load_scenario(tmp_path / "included.yaml")


def test_participant_packet_diffs_and_links_match_sources():
    packet = (ROOT / "README.md").read_text(encoding="utf-8")
    actual = re.findall(r"```diff\n(.*?)```", packet, re.DOTALL)
    pairs = [("baseline/included.yaml", "case-02/included.yaml"),
             ("baseline/flat.yaml", "case-01/flat.yaml"),
             ("baseline/child.yaml", "case-03/child.yaml")]
    expected = ["".join(difflib.unified_diff(
        (ROOT / before).read_text(encoding="utf-8").splitlines(keepends=True),
        (ROOT / after).read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile=before, tofile=after)) for before, after in pairs]
    assert actual == expected
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", packet)
    assert links
    for link in links:
        path = (ROOT / link).resolve()
        assert path.is_relative_to(ROOT)
        assert path.is_file()
    # Complete source and pin access must remain available, not only snippets.
    assert set(links) == {
        "baseline/included.yaml", "baseline/child.yaml", "baseline/included.includes.json", "baseline/flat.yaml",
        "case-02/included.yaml", "case-02/child.yaml", "case-02/included.includes.json", "case-01/flat.yaml",
        "case-03/included.yaml", "case-03/child.yaml", "case-03/included.includes.json"}
