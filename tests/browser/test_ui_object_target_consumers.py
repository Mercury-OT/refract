"""Actual object selection, actual HTTP effects, and isolated faulty targets."""
import json

import pytest

from examples.ui_object_targets.app import Application
from examples.ui_object_targets.run import ROOT, SCENARIO, run_case, target_hashes, verify_frozen_targets
from refracto.declaration.loader import load_scenario


def step(row, identity):
    return next(item for item in row["steps"] if item["id"] == identity)


def requests(row, method, path):
    return [item for item in row["server_requests"]
            if item["method"] == method and item["path"] == path]


@pytest.mark.parametrize("implementation", ["table", "cards"])
def test_same_scenario_selects_nonfirst_record_and_edits_only_its_object(implementation):
    row = run_case(implementation)
    assert row["status"] == "PASSED", row["steps"]
    assert row["degradation"] == []
    assert row["closed_contexts"] == 1
    assert [item["id"] for item in row["records"]] == ["r1", "r2", "r3"]
    assert row["records"][0]["name"] == "First record"
    assert row["records"][1]["name"] == "Second record"
    assert row["records"][2]["name"] == "Updated record"
    assert step(row, "open_editor")["selection"] == {
        "object_id": "r3", "object_matches": 1, "control_matches": 1}
    assert all(item["selection"] is None for item in row["steps"] if item["id"] != "open_editor")
    assert len(requests(row, "POST", "/api/records")) == 1
    assert len(requests(row, "GET", "/api/records/r3")) == 2  # Editor read, independent API read.
    assert len(requests(row, "PATCH", "/api/records/r3")) == 1
    assert not requests(row, "PATCH", "/api/records/r1")
    assert not requests(row, "PATCH", "/api/records/r2")


class MissingRow(Application):
    def response(self, method, path, body, headers):
        status, payload = super().response(method, path, body, headers)
        if method == "GET" and path == "/records":
            payload = {"records": [item for item in payload["records"] if item["id"] != "r3"]}
        return status, payload


class DuplicateRow(Application):
    def response(self, method, path, body, headers):
        status, payload = super().response(method, path, body, headers)
        if method == "GET" and path == "/records":
            payload = {"records": payload["records"] + [dict(self.records["r3"])]}
        return status, payload


class MissingIdentity(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = ("link.href = '/records/' + encodeURIComponent(record.id);" if name == "table.js"
                    else "form.setAttribute('action', '/records/' + encodeURIComponent(record.id));")
        assert source.count(original) == 1
        self.faults_applied = ["missing-identity"]
        return source.replace(original, "/* Separate faulty target omits its identity-bearing attribute. */").encode()


@pytest.mark.parametrize("implementation", ["table", "cards"])
@pytest.mark.parametrize("app_type", [MissingRow, DuplicateRow, MissingIdentity])
def test_invalid_row_evidence_does_not_click_or_send_an_edit_request(implementation, app_type):
    # Keep normal navigation/HTTP readiness on the same budget as the positive
    # consumer. Only the absent-object selection is expected to time out.
    row = run_case(implementation, app_type=app_type)
    assert row["status"] != "PASSED", row["steps"]
    assert step(row, "create")["status"] == "PASSED"
    assert step(row, "open_editor")["status"] == "ERROR"
    assert step(row, "open_editor")["selection"] is None
    assert step(row, "save")["status"] == "BLOCKED"
    assert not requests(row, "GET", "/api/records/r3")
    assert not any(item["method"] == "PATCH" for item in row["server_requests"])
    assert row["records"][2]["name"] == "Example record"
    assert row["closed_contexts"] == 1
    if app_type is MissingIdentity:
        assert row["target_faults"] == ["missing-identity"]


class WrongEdit(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = ("const path = link.getAttribute('href');" if name == "table.js"
                    else "const path = form.getAttribute('action');")
        assert source.count(original) == 1
        self.faults_applied = ["wrong-edit"]
        return source.replace(original, "const path = '/records/r1';").encode()


@pytest.mark.parametrize("implementation", ["table", "cards"])
def test_correct_row_receipt_cannot_hide_wrong_record_edit_request(implementation):
    row = run_case(implementation, app_type=WrongEdit)
    assert row["status"] != "PASSED", row["steps"]
    assert step(row, "open_editor")["status"] == "ERROR"
    assert row["target_faults"] == ["wrong-edit"]
    assert requests(row, "GET", "/api/records/r1")
    assert not requests(row, "GET", "/api/records/r3")
    assert not any(item["method"] == "PATCH" for item in row["server_requests"])
    assert step(row, "save")["status"] == "BLOCKED"


class WrongSave(Application):
    def script(self, name):
        source = super().script(name).decode()
        original = "const path = editor.getAttribute('action');"
        assert source.count(original) == 1
        self.faults_applied = ["wrong-save"]
        return source.replace(original, "const path = '/records/r1';").encode()


@pytest.mark.parametrize("implementation", ["table", "cards"])
def test_wrong_record_save_is_detected_even_after_a_real_side_effect(implementation):
    row = run_case(implementation, app_type=WrongSave)
    assert row["status"] != "PASSED", row["steps"]
    assert step(row, "open_editor")["status"] == "PASSED"
    assert step(row, "save")["status"] == "ERROR"
    assert row["target_faults"] == ["wrong-save"]
    assert step(row, "read_again")["status"] == "BLOCKED"
    assert len(requests(row, "PATCH", "/api/records/r1")) == 1
    assert not requests(row, "PATCH", "/api/records/r3")
    assert row["records"][0]["name"] == "Updated record"
    assert row["records"][2]["name"] == "Example record"


class ReorderedRows(Application):
    def response(self, method, path, body, headers):
        status, payload = super().response(method, path, body, headers)
        if method == "GET" and path == "/records":
            payload = {"records": list(reversed(payload["records"]))}
        return status, payload


@pytest.mark.parametrize("implementation", ["table", "cards"])
def test_selection_does_not_depend_on_list_order(implementation):
    row = run_case(implementation, app_type=ReorderedRows)
    assert row["status"] == "PASSED", row["steps"]
    assert step(row, "open_editor")["selection"]["object_id"] == "r3"
    assert len(requests(row, "PATCH", "/api/records/r3")) == 1


def test_normal_targets_stay_frozen_and_example_is_the_six_step_declaration():
    verify_frozen_targets()
    assert target_hashes() == json.loads((ROOT / "target-sources.json").read_text())["sha256"]
    assert [item.id for item in load_scenario(SCENARIO).steps] == [
        "create", "open_list", "open_editor", "fill_name", "save", "read_again"]
    for name in ("app.py", "table.js", "cards.js"):
        source = (ROOT / name).read_text()
        assert "data-" not in source


def test_normalizer_uses_actual_object_fields_without_repairing_them():
    from examples.ui_object_targets.adapter import Normalizer
    from refracto import ports
    normalizer = Normalizer()
    body = {"id": "independent-sample", "name": "Different actual content"}
    actual = ports.RecordedResponse(200, {}, body, "", None, ports.RequestSpec("GET", "records/x"))
    normalized = normalizer.normalize(actual)
    assert normalized.fields == body
    normalized.fields["id"] = "changed-owned-copy"
    assert actual.json["id"] == "independent-sample"
    absent = ports.RecordedResponse(200, {}, {}, "", None, ports.RequestSpec("GET", "records/x"))
    assert normalizer.normalize(absent).fields == {}
