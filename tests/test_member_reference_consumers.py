"""Bounded response selection against independent stateful public consumers."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from adapters.documents.normalizer import DocumentResponseNormalizer
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.query import request_path, wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    ("records", "list"): ROOT / "examples/minimal/create_locate_update_read.yaml",
    ("records", "dictionary"): ROOT / "examples/minimal/dictionary_record_reference.yaml",
    ("documents", "list"): ROOT / "examples/documents/scenarios/locate_update_read.yaml",
    ("documents", "dictionary"): ROOT / "examples/documents/scenarios/dictionary_document_reference.yaml",
}
PROJECTIONS = [("backend", "contract"), ("e2e",)]


class RecordsService:
    """Fixed behavior with actual stored records; never sees Scenario expectations."""

    def __init__(self, fault=None):
        self.records = {}
        self.requests = []
        self.authentications = []
        self.fault = fault

    def identify(self, user):
        if user != "creator":
            raise ValueError("unknown account")
        return "record-creator"

    def session(self, user):
        principal = self.identify(user)
        token = "records-session-" + str(len(self.authentications) + 1)
        self.authentications.append((principal, token))
        return ports.UserSession(principal_id=principal, authentication_id=token,
                                 credentials={"token": token})

    def send(self, request, session):
        method, path, body = request.method, request_path(request.path, request.query), request.body
        self.requests.append((method, path, deepcopy(body)))
        parsed = urlsplit(path)
        route = parsed.path.strip("/")
        if session.get("token") not in {token for _, token in self.authentications}:
            status, result = 401, {"error": "session_required"}
        elif method == "POST" and route in {"records", "records/enveloped"}:
            if not isinstance(body, dict) or set(body) != {"code", "name"}:
                status, result = 400, {"error": "invalid_record"}
            else:
                identifier = len(self.records) + 22
                record = {"id": identifier, **deepcopy(body)}
                self.records[identifier] = record
                status = 201
                result = {"record": deepcopy(record)} if route.endswith("enveloped") else {"accepted": True}
                if "record" in result:
                    if self.fault == "missing_key":
                        del result["record"]["id"]
                    elif self.fault == "null_key":
                        result["record"]["id"] = None
                    elif self.fault == "non_dictionary":
                        result["record"] = [deepcopy(record)]
        elif method == "GET" and route == "records":
            code = parse_qs(parsed.query).get("code", [None])[0]
            rows = [deepcopy(record) for record in self.records.values()
                    if code is None or record["code"] == code]
            if self.fault == "shuffle":
                rows.reverse()
            elif self.fault == "duplicate" and rows:
                rows.append(deepcopy(rows[-1]))
            elif self.fault == "missing_match":
                rows = []
            elif self.fault == "missing_key" and rows:
                rows[-1].pop("id")
            elif self.fault == "malformed_row":
                rows.append(None)
            status, result = 200, {"records": rows}
        else:
            parts = route.split("/")
            identifier = int(parts[-1]) if len(parts) == 2 and parts[-1].isdigit() else None
            record = self.records.get(identifier)
            if record is None:
                status, result = 404, {"error": "record_missing"}
            elif method == "PATCH" and isinstance(body, dict) and set(body) == {"name"}:
                record["name"] = body["name"]
                status, result = 200, deepcopy(record)
                if self.fault == "wrong_id":
                    result["id"] = identifier + 1000
            elif method == "GET":
                status, result = 200, deepcopy(record)
            else:
                status, result = 400, {"error": "invalid_request"}
        return ports.RecordedResponse(status, {}, result, json.dumps(result), None, request)


class RecordsNormalizer:
    def normalize(self, response):
        return ports.NormalizedResponse(200 <= response.status < 300,
                                        deepcopy(response.json), response.status, response)


class DocumentsFaults(DocumentRestApp):
    """Change observations at the actual target boundary, never manufacture expectations."""

    def __init__(self, fault=None):
        super().__init__()
        self.fault = fault

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        if response.status not in {200, 201}:
            return response
        data = deepcopy(response.body)
        if "result_set" in data:
            rows = data["result_set"]["nodes"]
            if self.fault == "shuffle":
                rows.reverse()
            elif self.fault == "duplicate" and rows:
                rows.append(deepcopy(rows[-1]))
            elif self.fault == "missing_match":
                rows.clear()
            elif self.fault == "missing_key" and rows:
                rows[-1].pop("identifier")
            elif self.fault == "malformed_row":
                rows.append(None)
        elif method == "POST" and "document" in data.get("resource", {}):
            document = data["resource"]["document"]
            if self.fault == "missing_key":
                document.pop("identifier")
            elif self.fault == "null_key":
                document["identifier"] = None
            elif self.fault == "non_dictionary":
                data["resource"]["document"] = [document]
        elif method == "PATCH" and self.fault == "wrong_id":
            data["resource"]["document"]["identifier"] = "wrong-document"
        return RestResponse(response.status, data, response.headers)


def consumer(kind, fault=None):
    if kind == "documents":
        app = DocumentsFaults(fault)
        return app, build_adapters(app)
    app = RecordsService(fault)
    return app, Adapters(auth=app, api=app, state=None, ui=None,
        recorder_factory=InMemoryRecorder, normalizer=RecordsNormalizer(),
        resolve_request=lambda template: ports.RequestSpec(
            template.method, template.path, deepcopy(template.body),
            query=wire_query(template.query or {}), headers=deepcopy(template.headers or {})))


def variant(tmp_path, path, change):
    raw = yaml.safe_load(path.read_text())
    change(raw)
    destination = tmp_path / "member-reference.yaml"
    destination.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return destination


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("shape", ["list", "dictionary"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_independent_consumers_use_real_selected_identifier(kind, shape, projections):
    app, adapters = consumer(kind)
    scenario = load_scenario(EXAMPLES[kind, shape])
    report = run_scenario(EXAMPLES[kind, shape], adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert all(domain.status == "PASSED" for domain in report.domains)
    assert len(app.requests) == len(scenario.steps)
    assert len(app.authentications) == 1
    records = report.domains[0].provider_recordings
    if shape == "dictionary":
        observed = records[0].json["record"] if kind == "records" else records[0].json["resource"]["document"]
        identifier = observed["id" if kind == "records" else "identifier"]
        assert app.requests[-1][1].endswith("/" + str(identifier))
    else:
        locate_index = next(index for index, step in enumerate(scenario.steps) if step.id == "locate")
        rows = adapters.normalizer.normalize(records[locate_index]).fields[
            "records" if kind == "records" else "documents"]
        selected = rows[-1]
        identifier = selected["id" if kind == "records" else "document_id"]
        assert app.requests[-2][1] == app.requests[-1][1]
        assert app.requests[-1][1].endswith("/" + str(identifier))
        if kind == "records":
            assert records[0].json == {"accepted": True}
            assert app.records[identifier]["name"] == "Updated record"
        else:
            assert len(rows) == 2 and rows[0]["document_id"] != identifier
            assert app._documents[identifier]["content"]["revision"] == 2


def test_approved_records_example_retains_the_four_step_obligations():
    raw = yaml.safe_load(EXAMPLES["records", "list"].read_text())
    assert raw["schema_version"] == 1 and raw["users"] == ["creator"]
    assert [step["id"] for step in raw["steps"]] == ["create", "locate", "update", "read"]
    assert [step.get("on_failure") for step in raw["steps"]] == ["stop", "stop", "stop", None]
    create, locate, update, read = raw["steps"]
    assert create["do"]["request"]["body"] == {
        "code": {"from_parameter": "record_code"}, "name": {"from_parameter": "original_name"}}
    assert locate["do"]["request"]["query"] == {"code": {"from_parameter": "record_code"}}
    reference = {"from_step": "locate", "response_field": "records",
        "matching": {"code": {"from_parameter": "record_code"}}, "member_field": "id"}
    assert update["do"]["request"]["path"] == ["records", reference]
    assert update["expect"]["response"][2] == {"check": "field_equals", "field": "id", "value": reference}
    assert read["do"]["request"]["path"][-1] == {"from_step": "update", "response_field": "id"}
    assert [check["field"] for check in read["expect"]["response"][2:]] == ["id", "code", "name"]


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", [None, "shuffle"])
def test_list_selection_does_not_depend_on_first_member_or_order(tmp_path, kind, projections, fault):
    def change(raw):
        if kind == "records":
            unrelated = deepcopy(raw["steps"][0])
            unrelated["id"] = "create_other"
            unrelated["do"]["request"]["body"] = {"code": "unrelated-code", "name": "Other record"}
            raw["steps"].insert(0, unrelated)
            raw["steps"][2]["do"]["request"].pop("query")
    app, adapters = consumer(kind, fault)
    path = variant(tmp_path, EXAMPLES[kind, "list"], change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert len(app.requests) == 5
    list_record = report.domains[0].provider_recordings[2]
    rows = adapters.normalizer.normalize(list_record).fields["records" if kind == "records" else "documents"]
    matching = [row for row in rows if row.get("code") == "record-example-001" or row.get("title") == "Selected document"]
    assert len(matching) == 1 and len(rows) == 2
    identifier = matching[0]["id" if kind == "records" else "document_id"]
    assert matching[0] == rows[0 if fault == "shuffle" else 1]
    assert app.requests[-2][1].endswith("/" + str(identifier))


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["duplicate", "missing_match", "missing_key", "malformed_row"])
def test_unavailable_list_evidence_blocks_without_relying_on_count_assertion(tmp_path, kind, projections, fault):
    def change(raw):
        step = next(step for step in raw["steps"] if step["id"] == "locate")
        step.pop("on_failure")
        # Make extraction, not a previous count assertion or stop policy, decisive.
        step["expect"]["response"] = [{"check": "status_equals", "value": 200}, {"check": "success"}]
    app, adapters = consumer(kind, fault)
    report = run_scenario(variant(tmp_path, EXAMPLES[kind, "list"], change), adapters, projections=projections)
    domain = report.domains[0]
    assert report.status != "PASSED"
    assert [step.status for step in domain.steps][-2:] == ["BLOCKED", "BLOCKED"]
    assert domain.steps[-2].resolved_bindings == {}
    assert all(method != "PATCH" for method, *_ in app.requests)
    assert len(app.requests) == (2 if kind == "records" else 3)
    if "contract" in projections:
        assert report.domains[1].status != "PASSED"


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["missing_key", "null_key", "non_dictionary"])
def test_unavailable_dictionary_member_blocks_before_another_request(tmp_path, kind, projections, fault):
    def change(raw):
        raw["steps"][0].pop("on_failure")
    app, adapters = consumer(kind, fault)
    report = run_scenario(variant(tmp_path, EXAMPLES[kind, "dictionary"], change), adapters, projections=projections)
    assert report.status != "PASSED"
    assert report.domains[0].steps[-1].status == "BLOCKED"
    assert report.domains[0].steps[-1].resolved_bindings == {}
    assert len(app.requests) == 1
    if "contract" in projections:
        assert report.domains[1].status != "PASSED"


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_wrong_update_response_id_is_not_a_valid_chain(kind, projections):
    app, adapters = consumer(kind, "wrong_id")
    report = run_scenario(EXAMPLES[kind, "list"], adapters, projections=projections)
    assert report.status == "FAILED"
    assert [step.status for step in report.domains[0].steps][-2:] == ["FAILED", "BLOCKED"]
    assert len(app.requests) == (3 if kind == "records" else 4)
    assert any(check.check == "field_equals" and not check.ok for check in report.domains[0].steps[-2].checks)
    if "contract" in projections:
        assert report.domains[1].status != "PASSED"


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_dictionary_selection_reads_envelope_not_an_existing_flat_alias(projections):
    class MisleadingCreateAlias(DocumentResponseNormalizer):
        def normalize(self, response):
            observed = super().normalize(response)
            if response.request.method == "POST":
                observed.fields["document_id"] = "not-the-observed-envelope-identifier"
            return observed
    app, adapters = consumer("documents")
    adapters.normalizer = MisleadingCreateAlias()
    report = run_scenario(EXAMPLES["documents", "dictionary"], adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert app.requests[-1][1] == "/v3/documents/document-1"
    source = adapters.normalizer.normalize(report.domains[0].provider_recordings[0])
    assert source.fields["document"]["identifier"] != source.fields["document_id"]


@pytest.mark.parametrize("kind", ["records", "documents"])
@pytest.mark.parametrize("shape", ["list", "dictionary"])
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_parameter_changes_are_carried_by_real_target_not_predetermined_results(tmp_path, kind, shape, projections):
    def change(raw):
        if kind == "records":
            raw["parameters"]["record_code"] = "different & code / + 002"
            raw["parameters"]["original_name" if shape == "list" else "record_name"] = "Changed input"
            if shape == "list":
                raw["parameters"]["updated_name"] = "Changed final name"
        else:
            raw["parameters"]["title"] = "A different title & + /"
            if shape == "list":
                raw["parameters"]["new_content"] = {"sections": [], "revision": 17}
    app, adapters = consumer(kind)
    path = variant(tmp_path, EXAMPLES[kind, shape], change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    source = yaml.safe_load(path.read_text())
    normalized = adapters.normalizer.normalize(report.domains[0].provider_recordings[-1]).fields
    if kind == "records":
        assert normalized["code"] == source["parameters"]["record_code"]
        assert normalized["name"] == source["parameters"]["updated_name" if shape == "list" else "record_name"]
    else:
        assert normalized["title"] == source["parameters"]["title"]
        if shape == "list":
            assert normalized["content"] == source["parameters"]["new_content"]
