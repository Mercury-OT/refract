"""Offline declaration and displayed-evidence checks for the live Flow example."""
import hashlib
import importlib
import json
from types import SimpleNamespace

import pytest
import yaml

from examples.browser_flow.adapter import read_rendered
from examples.browser_flow.run import FLOW
from refracto.declaration.loader import DeclarationError, load_flow, load_scenario
from refracto.report import CheckResult, DomainResult, FlowReport, FlowScenarioReport, StepResult


class DisplayPage:
    """Only the actual displayed result is available to the sample mapper."""

    def __init__(self, text, *, count=1, visible=True):
        self.text, self.elements, self.visible = text, count, visible

    def locator(self, selector):
        assert selector == "#result"
        return self

    def count(self):
        return self.elements

    def inner_text(self):
        return self.text

    def text_content(self):
        return self.text

    def is_visible(self):
        return self.visible


def display(data):
    return DisplayPage(json.dumps({"success": True, "data": data}))


def test_display_mapper_reads_actual_fields_without_repair_or_type_conversion():
    data = {"id": "r4", "name": "Observed name", "enabled": False, "count": 0,
            "empty": "", "nullable": None, "nested": {"items": [True, 1]}}
    page = display(data)
    original = page.text
    result = read_rendered(page)["records.result"]
    assert result == {"identified": [{"id": "r4", "fields": data}], "anonymous": []}
    fields = result["identified"][0]["fields"]
    assert type(fields["enabled"]) is bool
    assert type(fields["count"]) is int
    assert type(fields["nested"]["items"][0]) is bool
    assert type(fields["nested"]["items"][1]) is int
    fields["name"] = "Changed consumer copy"
    assert page.text == original
    assert read_rendered(page)["records.result"]["identified"][0]["fields"]["name"] == "Observed name"
    missing = read_rendered(display({"id": "r4"}))["records.result"]
    assert missing["identified"][0]["fields"] == {"id": "r4"}


@pytest.mark.parametrize("identity", [None, "", 0, 1, False, True, [], {}])
def test_display_mapper_does_not_guess_or_coerce_missing_business_identity(identity):
    data = {"name": "Observed name", "id": identity}
    actual = read_rendered(display(data))["records.result"]
    assert actual["identified"] == []
    assert actual["anonymous"] == [{"fields": data}]
    assert type(actual["anonymous"][0]["fields"]["id"]) is type(identity)


def test_empty_display_and_missing_identity_have_distinct_observations():
    assert read_rendered(DisplayPage("", visible=False)) == {
        "records.result": {"identified": [], "anonymous": []}}
    assert read_rendered(display({"name": "No exposed identity"})) == {
        "records.result": {"identified": [], "anonymous": [{"fields": {"name": "No exposed identity"}}]}}


@pytest.mark.parametrize("text", [
    "not JSON", "[]", "null", '{"data":{"id":"r4"}}',
    '{"success":1,"data":{"id":"r4"}}',
    '{"success":true,"data":[]}',
    '{"success":true,"data":{"id":"r4","id":"r5"}}',
    '{"success":true,"data":{"id":"r4","value":NaN}}',
    '{"success":true,"data":{"id":"r4","value":1e999}}',
])
def test_malformed_display_cannot_become_matching_evidence(text):
    with pytest.raises(ValueError):
        read_rendered(DisplayPage(text))


@pytest.mark.parametrize("count,visible", [(0, True), (2, True), (1, False)])
def test_missing_duplicate_or_hidden_display_is_not_visible_evidence(count, visible):
    page = DisplayPage('{"success":true,"data":{"id":"r4","name":"Observed"}}',
                       count=count, visible=visible)
    with pytest.raises(ValueError):
        read_rendered(page)


def test_hidden_nonempty_dom_is_not_confused_with_initial_empty_rendering():
    class HiddenPage(DisplayPage):
        def inner_text(self):
            return ""

    page = HiddenPage('{"success":true,"data":{"id":"r4"}}', visible=False)
    with pytest.raises(ValueError):
        read_rendered(page)


def test_approved_flow_pins_and_action_sequence_are_complete():
    plan = load_flow(FLOW)
    assert plan.id == "records.browser_lifecycle"
    assert plan.on_failure == "stop"
    assert plan.users == ["creator"]
    assert [(node.id, node.scenario_id) for node in plan.nodes] == [
        ("create", "records.browser_create"), ("update", "records.browser_update"),
        ("read", "records.browser_read")]
    assert all(node.with_users == {"operator": "creator"} for node in plan.nodes)
    assert [step.action for step in plan.scenario.steps] == [
        "open", "fill", "fill", "click", "fill", "fill", "click", "click"]
    assert [step.target for step in plan.scenario.steps] == [
        "records.page", "name", "code", "create", "record_id", "name", "update", "read"]
    assert [step.request.method for step in plan.scenario.steps if step.request] == ["POST", "PATCH", "GET"]
    documents = {name: yaml.safe_load(FLOW.with_name(name).read_text())
                 for name in (FLOW.name, "create.yaml", "update.yaml", "read.yaml")}
    assert all(document["schema_version"] == 1 for document in documents.values())
    assert documents["create.yaml"]["parameters"] == {"code": {"from_run": "unique"}}
    assert documents["create.yaml"]["write_flow"] == {
        "record_id": {"from_step": "submit", "response_field": "id"},
        "record_code": {"from_parameter": "code"}}
    assert documents["update.yaml"]["write_flow"] == {"expected_name": {"from_flow": "updated_name"}}
    assert "write_flow" not in documents["read.yaml"]
    manifest = json.loads(FLOW.with_suffix(".scenarios.json").read_text())
    assert manifest["manifest_version"] == 1
    assert set(manifest["scenarios"]) == {node.scenario_id for node in plan.nodes}
    for identity, dependency in manifest["scenarios"].items():
        path = FLOW.with_name(dependency["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == dependency["sha256"]
        assert yaml.safe_load(path.read_text())["scenario"] == identity


@pytest.mark.parametrize("name", ["create.yaml", "update.yaml", "read.yaml"])
def test_flow_dependent_declarations_reject_standalone_execution(name):
    with pytest.raises(DeclarationError):
        load_scenario(FLOW.with_name(name))


def test_target_inventory_freezes_only_the_three_unchanged_product_sources():
    runner = importlib.import_module("examples.browser_flow.run")
    inventory = json.loads((FLOW.parent / "target-sources.json").read_text())
    expected = {"examples/browser_multi_origin/" + name for name in ("app.py", "promise.js", "async.js")}
    assert inventory["manifest_version"] == 1
    assert set(inventory["sources"]) == expected
    assert inventory["baseline_commit"] == "522e0306744ab42642c9a204e71a282bc8dbc993"
    for name, digest in inventory["sources"].items():
        assert hashlib.sha256((runner.REPOSITORY / name).read_bytes()).hexdigest() == digest
    assert runner.verify_target_sources() == inventory["sources"]


def test_summary_retains_native_failures_without_publishing_actual_values():
    runner = importlib.import_module("examples.browser_flow.run")
    secret = "DO_NOT_PUBLISH_TEST_SECRET"
    step = StepResult("create/submit", "FAILED", [CheckResult("frontend", "objects_matching_count", False, secret)],
                      detail=secret, resolved_bindings={"value": secret})
    domain = DomainResult("e2e", [step], provider_recordings=[secret])
    node = FlowScenarioReport("records.browser_create", [domain], node_id="create")
    report = FlowReport("records.browser_lifecycle", secret, [node], parameter_history={"e2e": secret})
    bundle = SimpleNamespace(auth=SimpleNamespace(session_calls=[secret]),
                             ui=SimpleNamespace(opened=[secret], closed=[secret], actions=[secret]))
    result = runner.summarize(report, bundle, "promise")
    assert result["status"] == "FAILED"
    assert result["scenarios"][0]["domains"][0]["steps"][0]["checks"] == [
        {"point": "frontend", "check": "objects_matching_count", "ok": False}]
    assert set(result) == {"implementation", "flow_id", "status", "scenarios",
                           "session_acquisitions", "contexts_opened", "contexts_closed", "actions"}
    assert secret not in json.dumps(result)


@pytest.mark.parametrize("status,exit_code", [
    ("PASSED", 0), ("FAILED", 1), ("DEGRADED", 1), ("EMPTY", 1), ("NOT_SELECTED", 1),
])
def test_cli_requires_strict_pass_for_each_frontend(monkeypatch, capsys, status, exit_code):
    runner = importlib.import_module("examples.browser_flow.run")
    called = []

    def checked_run(implementation):
        called.append(implementation)
        return {"implementation": implementation, "status": status if implementation == "promise" else "PASSED"}

    monkeypatch.setattr(runner, "run", checked_run)
    assert runner.main() == exit_code
    assert called == ["promise", "async"]
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row["status"] for row in rows] == [status, "PASSED"]


def test_cli_execution_exception_is_nonzero_and_does_not_echo_its_message(monkeypatch, capsys):
    runner = importlib.import_module("examples.browser_flow.run")

    def failed_run(implementation):
        raise RuntimeError("DO_NOT_PUBLISH_RAW_EXCEPTION")

    monkeypatch.setattr(runner, "run", failed_run)
    assert runner.main() == 1
    output = capsys.readouterr().out
    assert "DO_NOT_PUBLISH_RAW_EXCEPTION" not in output
    rows = [json.loads(line) for line in output.splitlines()]
    assert len(rows) == 2
    assert all("status" not in row and "execution_error" in row for row in rows)
