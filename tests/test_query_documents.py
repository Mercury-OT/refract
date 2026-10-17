"""Query execution against the public Documents target, including real refusals."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
import yaml

from adapters.documents.wiring import build_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from refracto.runner import run_scenario


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/documents/scenarios/filter_and_next_page.yaml"
PROJECTIONS = [("backend", "contract"), ("e2e",)]


def write_example(tmp_path, change):
    declaration = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(declaration)
    path = tmp_path / "query_documents.yaml"
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return path


def observed_queries(app):
    return [dict(parse_qsl(urlsplit(path).query, keep_blank_values=True))
            for method, path, _, _ in app.requests if method == "GET"]


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_approved_five_step_example_follows_observed_cursor(projections):
    # Each projection selection receives a fresh target, with no adapter reset.
    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(EXAMPLE, adapters, projections=projections)

    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert [step.step_id for step in report.domains[0].steps] == [
        "create_first", "create_other_category", "create_second", "first_page", "next_page"]
    assert [record.status for record in report.domains[0].provider_recordings] == [201, 201, 201, 200, 200]
    assert app.request_count == 5  # Contract consumes recordings without sending.
    assert len(app.authentications) == 1
    assert [body for _, _, body, _ in app.requests[:3]] == [
        {"title": "Getting started", "category": "guide"},
        {"title": "Internal memo", "category": "memo"},
        {"title": "Advanced usage", "category": "guide"},
    ]
    assert observed_queries(app) == [
        {"category": "guide", "limit": "1", "cursor": "0"},
        {"category": "guide", "limit": "1", "cursor": "1"},
    ]
    records = report.domains[0].provider_recordings
    normalized = [adapters.normalizer.normalize(record).fields for record in records]
    assert normalized[3] == {
        "documents": [{"document_id": normalized[0]["document_id"],
                       "title": "Getting started", "category": "guide"}],
        "returned": 1, "next_cursor": 1,
    }
    assert normalized[4] == {
        "documents": [{"document_id": normalized[2]["document_id"],
                       "title": "Advanced usage", "category": "guide"}],
        "returned": 1, "next_cursor": None,
    }
    assert normalized[0]["document_id"] != normalized[2]["document_id"]
    for record, actual_query in zip(records[3:], observed_queries(app), strict=True):
        assert record.request.path == "/v3/documents"
        assert record.request.query == actual_query
        assert record.actual_path == "/v3/documents"
        assert record.template_path == "documents/search"
    cursor_source = [source for source in report.domains[0].steps[-1].binding_sources.values()
                     if source.response_field == "next_cursor"]
    assert len(cursor_source) == 1
    assert cursor_source[0].origin.step_id == "first_page"
    assert cursor_source[0].origin.is_final is True
    assert cursor_source[0].origin.user == "editor"


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_documents_query_encoding_reaches_target_once_and_ignores_global_defaults(tmp_path, projections):
    category = "\u8a18\u9332 + & = % / guide"

    def change(declaration):
        declaration["parameters"].update({
            "category": category,
            # These formerly implicit resolver inputs must have no effect.
            "filter_category": "memo", "cursor": -1, "page_size": 0,
        })

    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(write_example(tmp_path, change), adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert app.request_count == 5
    assert [query["category"] for query in observed_queries(app)] == [category, category]
    for sent in adapters.api.sent[-2:]:
        assert sent.query["category"] == category
        assert category not in repr(sent)


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("query", [None, {}], ids=["omitted", "empty"])
def test_documents_omitted_or_empty_query_sends_no_implicit_parameters(tmp_path, projections, query):
    def change(declaration):
        declaration["parameters"].update({"filter_category": "memo", "cursor": 1, "page_size": 1})
        declaration["steps"] = declaration["steps"][:4]
        request = declaration["steps"][-1]["do"]["request"]
        if query is None:
            request.pop("query")
        else:
            request["query"] = query
        declaration["steps"][-1]["expect"]["response"] = [
            {"check": "status_equals", "value": 200}, {"check": "success"},
            {"check": "field_equals", "field": "returned", "value": 3},
        ]

    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(write_example(tmp_path, change), adapters, projections=projections)
    assert report.status == "PASSED", report.localize()
    assert app.request_count == 4
    assert app.requests[-1][1] == "/v3/documents"
    assert adapters.api.sent[-1].query == {}
    assert observed_queries(app) == [{}]


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("key,value,status,expected_titles", [
    ("category", "memo", 200, ["Internal memo"]),
    ("category", "unknown", 200, []),
    ("limit", 2, 200, ["Getting started", "Advanced usage"]),
    ("cursor", 1, 200, ["Advanced usage"]),
    ("cursor", "not-numeric", 400, None),
    ("cursor", -1, 400, None),
    ("limit", 0, 400, None),
])
def test_wrong_declared_query_is_observed_by_target_and_cannot_pass_response_checks(
        tmp_path, projections, key, value, status, expected_titles):
    def change(declaration):
        declaration["steps"][3]["do"]["request"]["query"][key] = value

    app = DocumentRestApp()
    adapters = build_adapters(app)
    report = run_scenario(write_example(tmp_path, change), adapters, projections=projections)
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED"] * 3 + ["FAILED", "BLOCKED"]
    assert app.request_count == 4  # first_page's explicit stop blocks next_page.
    assert observed_queries(app)[0][key] == str(value)
    record = domain.provider_recordings[-1]
    assert record.status == status
    fields = adapters.normalizer.normalize(record).fields
    if expected_titles is None:
        assert record.json["receipt"]["state"] == "rejected"
        assert record.json["fault"]["code"] == "page_invalid"
        assert fields["error_code"] == "page_invalid"
    else:
        assert [member["title"] for member in fields["documents"]] == expected_titles
    assert any(not check.ok and check.step == "first_page" for check in domain.checks)
    if "contract" in projections:
        assert report.domains[1].status == "FAILED"


class ChangedFirstCursor(DocumentRestApp):
    """Change an actual target response, independently of the declaration."""

    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    def handle(self, method, path, body=None, headers=None):
        response = super().handle(method, path, body, headers)
        query = dict(parse_qsl(urlsplit(path).query))
        if method != "GET" or response.status != 200 or query.get("cursor") != "0":
            return response
        changed = deepcopy(response.body)
        page = changed["result_set"]["page_info"]
        if self.fault == "missing":
            page.pop("next_cursor")
        else:
            page["next_cursor"] = {"null": None, "list": [1], "object": {"cursor": 1},
                                   "negative": -1, "text": "not-numeric"}[self.fault]
        return RestResponse(response.status, changed, response.headers)


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["missing", "null", "list", "object"])
def test_unusable_observed_cursor_blocks_dependent_query_atomically(tmp_path, projections, fault):
    def change(declaration):
        # Permit continuation so dependency handling, not explicit stop, is tested.
        declaration["steps"][3].pop("on_failure")
        declaration["steps"].append({
            "id": "independent_read", "do": {"request": {
                "method": "GET", "path": ["documents", "search"], "query": {}}},
            "expect": {"response": [{"check": "status_equals", "value": 200},
                                    {"check": "success"}]},
        })

    app = ChangedFirstCursor(fault)
    adapters = build_adapters(app)
    report = run_scenario(write_example(tmp_path, change), adapters, projections=projections)
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED"] * 3 + ["FAILED", "BLOCKED", "PASSED"]
    assert domain.steps[4].blocked_by == ["first_page"]
    assert domain.steps[4].resolved_bindings == {}
    assert app.request_count == 5
    assert observed_queries(app) == [{"category": "guide", "limit": "1", "cursor": "0"}, {}]
    page = domain.provider_recordings[3].json["result_set"]["page_info"]
    if fault == "missing":
        assert "next_cursor" not in page
    else:
        assert page["next_cursor"] == {"null": None, "list": [1], "object": {"cursor": 1}}[fault]


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault,wire_value", [("negative", "-1"), ("text", "not-numeric")])
def test_scalar_cursor_is_sent_and_real_target_rejects_invalid_pagination(tmp_path, projections, fault, wire_value):
    path = write_example(tmp_path, lambda declaration: declaration["steps"][3].pop("on_failure"))
    app = ChangedFirstCursor(fault)
    adapters = build_adapters(app)
    report = run_scenario(path, adapters, projections=projections)
    domain = report.domains[0]
    assert report.status == "FAILED"
    assert [step.status for step in domain.steps] == ["PASSED"] * 3 + ["FAILED", "FAILED"]
    assert app.request_count == 5
    assert observed_queries(app)[1]["cursor"] == wire_value
    rejected = domain.provider_recordings[-1]
    assert rejected.status == 400
    assert rejected.request.query["cursor"] == wire_value
    assert rejected.json["fault"]["code"] == "page_invalid"
    assert adapters.normalizer.normalize(rejected).succeeded is False
