"""Numeric and list bounds against two independent stateful consumers."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.projection import contract
from refracto.query import request_path, wire_query
from refracto.recorder import InMemoryRecorder
from refracto.runner import Adapters, run_scenario


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "documents": ROOT / "examples/documents/scenarios/check_page_limits.yaml",
    "records": ROOT / "examples/minimal/check_page_limits.yaml",
}
PROJECTIONS = [("backend", "contract"), ("e2e",)]


class RecordsService:
    """Own storage and pagination; no scenario or expected value enters this service."""

    def __init__(self, fault=None):
        self.fault = fault
        self.records = {}
        self.requests = []
        self.authentications = []
        self.emitted = []
        self.emitted_snapshots = []
        self.before_reads = None

    def identify(self, user):
        if user != "creator":
            raise ValueError("unknown account")
        return "record-creator"

    def session(self, user):
        principal = self.identify(user)
        token = "record-session-" + str(len(self.authentications) + 1)
        self.authentications.append((principal, token))
        return ports.UserSession(principal_id=principal, authentication_id=token,
                                 credentials={"token": token})

    def send(self, request, session):
        path = request_path(request.path, request.query)
        self.requests.append((request.method, path, deepcopy(request.body)))
        parsed = urlsplit(path)
        if session.get("token") not in {token for _, token in self.authentications}:
            status, result = 401, {"error": "session_required"}
        elif parsed.path.strip("/") != "records":
            status, result = 404, {"error": "route_missing"}
        elif request.method == "POST":
            body = request.body
            if not isinstance(body, dict) or set(body) != {"title", "category"}:
                status, result = 400, {"error": "invalid_record"}
            else:
                identifier = len(self.records) + 41
                record = {"id": identifier, **deepcopy(body)}
                self.records[identifier] = record
                # Fixed service metadata is available as an actual prior threshold.
                status, result = 201, {**deepcopy(record), "page_limit": 2}
        elif request.method == "GET":
            if self.before_reads is None:
                self.before_reads = deepcopy(self.records)
            status, result = self._page(parse_qs(parsed.query))
        else:
            status, result = 405, {"error": "method_not_allowed"}
        self.emitted.append(result)
        self.emitted_snapshots.append(deepcopy(result))
        return ports.RecordedResponse(status, {}, result, json.dumps(result), None, request)

    def _page(self, query):
        try:
            cursor = int(query.get("cursor", ["0"])[0])
            limit = int(query.get("limit", ["10"])[0])
        except ValueError:
            return 400, {"error": "page_invalid"}
        if cursor < 0 or limit < 1:
            return 400, {"error": "page_invalid"}
        category = query.get("category", [None])[0]
        matching = [record for record in self.records.values()
                    if category is None or record["category"] == category]
        if self.fault == "ignored_filter":
            matching = list(self.records.values())
        if self.fault == "repeated_first_page":
            cursor = 0
        page = deepcopy(matching[cursor:cursor + limit])
        result = {"records": page, "returned": len(page),
                  "next_cursor": cursor + limit if cursor + limit < len(matching) else None}
        if self.fault == "oversized":
            # Retain a plausible reported count while returning too many real rows.
            result["records"] = deepcopy(matching[cursor:cursor + limit + 1])
        elif self.fault == "empty":
            result["records"] = []
        elif self.fault == "wrong_collection":
            result["records"] = {"unexpected": page}
        elif self.fault == "missing_collection":
            del result["records"]
        elif self.fault == "null_cursor":
            result["next_cursor"] = None
        elif self.fault == "missing_cursor":
            del result["next_cursor"]
        elif self.fault in {"false_count", "zero_count", "text_count", "null_count"}:
            result["returned"] = {"false_count": False, "zero_count": 0,
                                  "text_count": "1", "null_count": None}[self.fault]
        return 200, result


class RecordsNormalizer:
    def normalize(self, response):
        # Preserve both observations independently; never repair a reported count.
        return ports.NormalizedResponse(200 <= response.status < 300,
                                        deepcopy(response.json), response.status, response)


class DocumentsFaults(DocumentRestApp):
    """Faults act on the real target's queries and returned bodies."""

    def __init__(self, fault=None):
        super().__init__()
        self.fault = fault
        self.emitted = []
        self.emitted_snapshots = []
        self.before_reads = None

    def _list(self, query, principal):
        changed = deepcopy(query)
        if self.fault == "ignored_filter":
            changed.pop("category", None)
        elif self.fault == "repeated_first_page":
            changed["cursor"] = ["0"]
        elif self.fault == "oversized":
            changed["limit"] = [str(int(changed["limit"][0]) + 1)]
        return super()._list(changed, principal)

    def handle(self, method, path, body=None, headers=None):
        if method == "GET" and self.before_reads is None:
            self.before_reads = deepcopy(self._documents)
        response = super().handle(method, path, body, headers)
        data = deepcopy(response.body)
        if method == "GET" and response.status == 200:
            result = data["result_set"]
            if self.fault == "empty":
                result["nodes"] = []
            elif self.fault == "wrong_collection":
                result["nodes"] = {"unexpected": result["nodes"]}
            elif self.fault == "missing_collection":
                del result["nodes"]
            elif self.fault == "null_cursor":
                result["page_info"]["next_cursor"] = None
            elif self.fault == "missing_cursor":
                del result["page_info"]["next_cursor"]
        self.emitted.append(data)
        self.emitted_snapshots.append(deepcopy(data))
        return RestResponse(response.status, data, response.headers)


def consumer(kind, fault=None):
    if kind == "documents":
        target = DocumentsFaults(fault)
        return target, build_adapters(target)
    target = RecordsService(fault)
    return target, Adapters(auth=target, api=target, state=None, ui=None,
        recorder_factory=InMemoryRecorder, normalizer=RecordsNormalizer(),
        resolve_request=lambda scenario, step, template: ports.RequestSpec(
            template.method, template.path, deepcopy(template.body),
            query=wire_query(template.query or {})))


def variant(tmp_path, kind, change):
    declaration = yaml.safe_load(EXAMPLES[kind].read_text())
    change(declaration)
    path = tmp_path / "numeric-consumer.yaml"
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


def numeric_checks(step):
    return [check.ok for check in step.checks
            if check.check in {"field_compare", "collection_length"}]


def queries(target):
    return [{key: values[0] for key, values in parse_qs(urlsplit(path).query).items()}
            for method, path, *_ in target.requests if method == "GET"]


@pytest.mark.parametrize("kind", EXAMPLES)
@pytest.mark.parametrize("projections", PROJECTIONS)
def test_real_isolated_consumers_follow_two_pages_without_mutating_evidence(kind, projections):
    target, adapters = consumer(kind)
    report = run_scenario(EXAMPLES[kind], adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert all(domain.status == "PASSED" for domain in report.domains)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED"] * 5
    assert [record.status for record in domain.provider_recordings] == [201, 201, 201, 200, 200]
    assert len(target.requests) == 5 and len(target.authentications) == 1
    assert queries(target) == [{"category": "guide", "limit": "1", "cursor": "0"},
                               {"category": "guide", "limit": "1", "cursor": "1"}]
    fields = [adapters.normalizer.normalize(record).fields for record in domain.provider_recordings]
    identifier, collection = ("document_id", "documents") if kind == "documents" else ("id", "records")
    assert fields[0][identifier] != fields[2][identifier]
    assert fields[3][collection] == [{key: fields[0][key] for key in (identifier, "title", "category")}]
    assert fields[4][collection] == [{key: fields[2][key] for key in (identifier, "title", "category")}]
    assert fields[3]["next_cursor"] == 1 and fields[4]["next_cursor"] is None
    assert numeric_checks(domain.steps[3]) == numeric_checks(domain.steps[4]) == [True] * 4
    cursor_sources = [source for source in domain.steps[4].binding_sources.values()
                      if source.response_field == "next_cursor"]
    assert len(cursor_sources) == 1 and cursor_sources[0].origin.step_id == "first_page"
    assert cursor_sources[0].origin.is_final is True

    scenario = load_scenario(EXAMPLES[kind])
    scenario_snapshot = deepcopy(scenario)
    recordings_snapshot = deepcopy(domain.provider_recordings)
    replay = contract.run(scenario, domain.provider_recordings, adapters.normalizer,
                          execution_steps=domain.steps)
    assert replay.status == "PASSED"
    assert scenario == scenario_snapshot and domain.provider_recordings == recordings_snapshot
    assert target.emitted == target.emitted_snapshots
    assert [record.json for record in domain.provider_recordings] == target.emitted_snapshots
    assert (target._documents if kind == "documents" else target.records) == target.before_reads
    assert len(target.requests) == 5  # Contract replay performs no service action.


@pytest.mark.parametrize("kind", EXAMPLES)
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["empty", "oversized", "wrong_collection", "missing_collection"])
def test_actual_empty_oversized_or_wrong_type_page_cannot_pass(kind, projections, fault):
    target, adapters = consumer(kind, fault)
    report = run_scenario(EXAMPLES[kind], adapters, projections=projections)
    assert report.status == "FAILED"
    assert all(domain.status == "FAILED" for domain in report.domains)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED"] * 3 + ["FAILED", "BLOCKED"]
    assert len(target.requests) == 4
    length_checks = [check.ok for check in domain.steps[3].checks if check.check == "collection_length"]
    assert length_checks == {"empty": [False, True], "oversized": [True, False],
                             "wrong_collection": [False, False], "missing_collection": [False, False]}[fault]
    if kind == "records":
        observed = domain.provider_recordings[3].json
        assert observed["returned"] == 1
        assert [check.ok for check in domain.steps[3].checks if check.check == "field_compare"] == [True, True]
    assert target.emitted == target.emitted_snapshots


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault,expected", [
    ("false_count", [False, False]), ("zero_count", [False, True]),
    ("text_count", [False, False]), ("null_count", [False, False]),
])
def test_reported_count_is_checked_without_repairing_it_from_the_actual_list(projections, fault, expected):
    target, adapters = consumer("records", fault)
    report = run_scenario(EXAMPLES["records"], adapters, projections=projections)
    assert report.status == "FAILED"
    assert all(domain.status == "FAILED" for domain in report.domains)
    step = report.domains[0].steps[3]
    assert [check.ok for check in step.checks if check.check == "field_compare"] == expected
    assert [check.ok for check in step.checks if check.check == "collection_length"] == [True, True]
    assert len(report.domains[0].provider_recordings[3].json["records"]) == 1
    assert len(target.requests) == 4


@pytest.mark.parametrize("kind", EXAMPLES)
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["ignored_filter", "repeated_first_page"])
def test_correct_bounds_do_not_hide_wrong_filter_or_repeated_page(kind, projections, fault):
    target, adapters = consumer(kind, fault)
    report = run_scenario(EXAMPLES[kind], adapters, projections=projections)
    assert report.status == "FAILED"
    assert all(domain.status == "FAILED" for domain in report.domains)
    domain = report.domains[0]
    assert [step.status for step in domain.steps] == ["PASSED"] * 4 + ["FAILED"]
    assert numeric_checks(domain.steps[4]) == [True] * 4
    membership = [check for check in domain.steps[4].checks if check.check == "collection_matching_count"]
    assert len(membership) == 1 and membership[0].ok is False
    assert queries(target)[1]["cursor"] == "1"
    assert len(target.requests) == 5


@pytest.mark.parametrize("kind", EXAMPLES)
@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["missing_cursor", "null_cursor"])
def test_unavailable_cursor_blocks_only_dependent_page_when_continuation_allowed(tmp_path, kind, projections, fault):
    def change(raw):
        raw["steps"][3].pop("on_failure")
        raw["steps"].append({"id": "independent", "do": {"request": {
            "method": "GET", "path": ["documents", "search"] if kind == "documents" else ["records"]}},
            "expect": {"response": [{"check": "status_equals", "value": 200}, {"check": "success"}]}})
    target, adapters = consumer(kind, fault)
    report = run_scenario(variant(tmp_path, kind, change), adapters, projections=projections)
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED"] * 3 + ["FAILED", "BLOCKED", "PASSED"]
    assert domain.steps[4].resolved_bindings == {}
    assert domain.steps[4].blocked_by == ["first_page"]
    assert len(target.requests) == 5 and queries(target)[1] == {}


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_numeric_thresholds_use_actual_prior_service_value_and_contract_recomputes_it(tmp_path, projections):
    def change(raw):
        raw["steps"] = raw["steps"][:4]
        raw["steps"][0]["expect"]["response"].append(
            {"check": "field_compare", "field": "page_limit", "op": ">=", "value": 1})
        page = raw["steps"][3]
        page["do"]["request"]["query"]["limit"] = 2
        source = {"from_step": "create_first", "response_field": "page_limit"}
        page["expect"]["response"] = [
            {"check": "status_equals", "value": 200}, {"check": "success"},
            {"check": "field_compare", "field": "returned", "op": "<=", "value": source},
            {"check": "collection_length", "field": "records", "op": "<=", "value": deepcopy(source)},
        ]
    target, adapters = consumer("records")
    path = variant(tmp_path, "records", change)
    report = run_scenario(path, adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    domain = report.domains[0]
    assert domain.provider_recordings[0].json["page_limit"] == 2
    assert domain.provider_recordings[3].json["returned"] == 2
    assert set(domain.steps[3].resolved_bindings.values()) == {2}
    assert numeric_checks(domain.steps[3]) == [True, True]
    changed = deepcopy(domain.provider_recordings)
    changed[0].json["page_limit"] = 1
    replay = contract.run(load_scenario(path), changed, adapters.normalizer,
                          execution_steps=domain.steps)
    assert replay.status == "FAILED"
    assert any(not check.ok and check.step == "first_page" for check in replay.checks)
    assert domain.provider_recordings[0].json["page_limit"] == 2
    assert len(target.requests) == 4
