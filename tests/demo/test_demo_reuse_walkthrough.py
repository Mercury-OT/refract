"""Run the approved minimal reuse example without changing its obligations."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import yaml

from adapters.demo.wiring import build_adapters
from refracto.declaration.binding import prepare_step
from refracto.declaration.loader import load_scenario
from refracto.declaration.model import ResultSource
from refracto.ports import NormalizedResponse
from refracto.runner import run_scenario


EXAMPLE = Path(__file__).resolve().parents[2] / "examples/scenario-reuse"
CHILD = EXAMPLE / "shared/create_item.yaml"
PARENT = EXAMPLE / "create_read.yaml"


def checks(step):
    return {point: [{"check": assertion.check, **assertion.params}
                    for assertion in getattr(step.expect, point)]
            for point in ("frontend", "response", "backend_state")}


def test_walkthrough_sources_retain_the_approved_minimal_pair():
    """Explicit expectations prevent silently broadening the walkthrough."""
    assert yaml.safe_load(CHILD.read_text(encoding="utf-8")) == {
        "schema_version": 1, "scenario": "shared.create_item", "actor": "user",
        "parameters": {"item_name": "Default record"},
        "steps": [{
            "id": "create_request",
            "do": {"request": {"method": "POST", "path": ["items"],
                               "body": {"name": {"from_parameter": "item_name"}}}},
            "expect": {"response": [
                {"check": "success"}, {"check": "has", "field": "itemId"},
                {"check": "field_equals", "field": "name",
                 "value": {"from_parameter": "item_name"}}],
                "backend_state": [{"check": "span_exists", "span": "item.create"}]},
        }],
        "results": {
            "record_id": {"from_step": "create_request", "response_field": "itemId"},
            "record_name": {"from_step": "create_request", "response_field": "name"}},
    }
    assert yaml.safe_load(PARENT.read_text(encoding="utf-8")) == {
        "schema_version": 1, "scenario": "demo.create_read", "actor": "user",
        "parameters": {"record_name": "Test record"},
        "steps": [
            {"id": "setup", "do": {"include": "shared.create_item"},
             "with": {"item_name": {"from_parameter": "record_name"}}},
            {"id": "read", "do": {"request": {"method": "GET", "path": ["items"]}},
             "expect": {"response": [
                 {"check": "success"},
                 {"check": "collection_matching_count", "field": "items",
                  "matching": {"id": {"from_step": "setup", "result": "record_id"},
                               "name": {"from_parameter": "record_name"}}, "count": 1}]}}],
    }


def test_walkthrough_exact_pin_and_named_result_sources():
    digest = hashlib.sha256(CHILD.read_bytes()).hexdigest()
    assert json.loads(PARENT.with_suffix(".includes.json").read_text(encoding="utf-8")) == {
        "manifest_version": 1,
        "scenarios": {"shared.create_item": {
            "path": "shared/create_item.yaml", "sha256": digest}}}
    child = load_scenario(CHILD)
    parent = load_scenario(PARENT)
    assert child.id == "shared.create_item"
    assert child.actor == parent.actor == "user"
    assert child.parameters == {"item_name": "Default record"}
    assert child.results == {
        "record_id": ResultSource("create_request", "itemId"),
        "record_name": ResultSource("create_request", "name"),
    }
    assert [step.id for step in parent.steps] == ["setup/create_request", "read"]
    assert parent.source_lookup["setup/create_request"] == {
        "scenario_id": "shared.create_item", "step_id": "create_request",
        "include_step_id": "setup", "sha256": digest,
    }
    assert parent.included_results == {"setup": {
        "record_id": ResultSource("setup/create_request", "itemId"),
        "record_name": ResultSource("setup/create_request", "name"),
    }}
    assert {(binding.from_step, binding.field) for binding in parent.steps[1].bind} == {
        ("setup/create_request", "itemId")}


@pytest.mark.parametrize("observed_id", (41, 907))
def test_walkthrough_materializes_real_result_reference_not_observed_name(observed_id):
    parent = load_scenario(PARENT)
    create, create_bindings = prepare_step(parent.steps[0], parent, {})
    assert create.action == "request"
    assert (create.request.method, create.request.path, create.request.body) == (
        "POST", "items", {"name": "Test record"})
    assert create_bindings == {}
    assert checks(create) == {
        "frontend": [],
        "response": [{"check": "success"}, {"check": "has", "field": "itemId"},
                     {"check": "field_equals", "field": "name", "value": "Test record"}],
        "backend_state": [{"check": "span_exists", "span": "item.create"}],
    }
    # This is a binding probe, not a successful execution: a different observed
    # name must not replace the parent's independently chosen input expectation.
    prior = {"setup/create_request": NormalizedResponse(
        True, {"itemId": observed_id, "name": "Not the requested name"}, 200, None)}
    read, bindings = prepare_step(parent.steps[1], parent, prior)
    assert (read.request.method, read.request.path, read.request.body) == ("GET", "items", None)
    assert list(bindings.values()) == [observed_id]
    assert checks(read) == {
        "frontend": [],
        "response": [{"check": "success"}, {
            "check": "collection_matching_count", "field": "items",
            "matching": {"id": observed_id, "name": "Test record"}, "count": 1}],
        "backend_state": [],
    }


@pytest.mark.parametrize("existing_name", ("Unrelated record", "Test record"))
def test_walkthrough_executes_real_demo_with_an_unrelated_record(demo_server, existing_name):
    # Ordinary test setup creates a distinct business object; it does not alter
    # the approved Scenario, its adapter, or the app to make the test pass.
    seeded = httpx.post(f"{demo_server}/items", json={"name": existing_name}, timeout=5)
    seeded.raise_for_status()
    assert seeded.json()["success"] is True
    existing_id = seeded.json()["data"]["itemId"]

    report = run_scenario(PARENT, build_adapters(demo_server), projections=("backend",))
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert [domain.projection for domain in report.domains] == ["backend"]
    domain = report.domains[0]
    assert [(step.step_id, step.status) for step in domain.steps] == [
        ("setup/create_request", "PASSED"), ("read", "PASSED")]
    assert [(check.point, check.check, check.ok) for check in domain.checks] == [
        ("response", "success", True), ("response", "has", True),
        ("response", "field_equals", True), ("backend_state", "span_exists", True),
        ("response", "success", True), ("response", "collection_matching_count", True)]
    creation, listing = domain.provider_recordings
    assert [record.step_id for record in domain.provider_recordings] == [
        "setup/create_request", "read"]
    assert creation.request.body == {"name": "Test record"}
    created_id = creation.json["data"]["itemId"]
    assert created_id != existing_id
    assert creation.json["data"]["name"] == "Test record"
    assert list(domain.steps[1].resolved_bindings.values()) == [created_id]
    members = listing.json["data"]["items"]
    assert len(members) == 2
    assert {member["id"] for member in members} == {existing_id, created_id}
    assert sum(member["id"] == created_id and member["name"] == "Test record"
               for member in members) == 1
    assert report.source_lookup == load_scenario(PARENT).source_lookup
