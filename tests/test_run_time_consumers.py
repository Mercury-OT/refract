"""Frozen time inputs against stateful targets, with explicit evidence limits."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from adapters.documents.wiring import build_adapters as document_adapters
from examples.documents.app import DocumentRestApp, RestResponse
from examples.minimal.adapters import build_adapters as record_adapters
from examples.minimal.app import AppResponse, MinimalRestApp
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import load_scenario
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "examples/minimal/create_expiring_record.yaml"
DOCUMENTS = ROOT / "examples/documents/scenarios/query_recent_documents.yaml"
BASE = "2026-10-24T08:00:00.000Z"
PROJECTIONS = [("backend", "contract"), ("e2e",)]


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ExpiringRecords(MinimalRestApp):
    """A target extension storing supplied expiration; it never sees assertions."""

    def __init__(self, fault=None):
        super().__init__()
        self.fault = fault

    def handle(self, method, path, body=None):
        result = super().handle(method, path, body)
        if method == "POST" and result.status == 201:
            item = self._items[result.body["id"]]
            item["expires_at"] = body["expires_at"]
            return AppResponse(201, deepcopy(item), result.headers)
        if method == "GET" and result.status == 200 and self.fault:
            observed = deepcopy(result.body)
            if self.fault == "missing":
                observed.pop("expires_at")
            elif self.fault == "wrong_time":
                observed["expires_at"] = "2000-01-01T00:00:00.000Z"
            elif self.fault == "null":
                observed["expires_at"] = None
            return AppResponse(200, observed, result.headers)
        return result


class TimedDocuments(DocumentRestApp):
    """Separate target-side clock and filtering, without reading Scenario data."""

    def __init__(self, fault=None):
        super().__init__()
        self.fault = fault
        self.server_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
        self.created_at = {}

    def _create(self, body, principal):
        result = super()._create(body, principal)
        if result.status == 201:
            identifier = result.body["resource"]["document"]["identifier"]
            self.created_at[identifier] = self.server_time
        return result

    def _list(self, query, principal):
        # This fixture endpoint defines an inclusive interval at both ends.
        start = instant(query["created_from"][0])
        end = instant(query["created_to"][0])
        selected = []
        for identifier, document in self._documents.items():
            if self._owners[identifier] != principal:
                continue
            created = self.created_at[identifier]
            inside = start <= created <= end
            if self.fault == "ignored_filter":
                inside = True
            elif self.fault == "excluded_boundaries":
                inside = start < created < end
            elif self.fault == "empty":
                inside = False
            if inside:
                selected.append(deepcopy(document))
        cursor, limit = int(query["cursor"][0]), int(query["limit"][0])
        page = selected[cursor:cursor + limit]
        return RestResponse(200, {
            "receipt": {"state": "accepted", "operation": "list"},
            "result_set": {"nodes": page, "page_info": {"next_cursor": None}},
        }, {"content-type": "application/json"})


def seeded_documents(base=BASE, fault=None):
    """Prepare known independent data, including both one-millisecond neighbors."""
    app = TimedDocuments(fault)
    _, token = app.authenticate("reader")
    end = instant(base)
    start = end - timedelta(hours=24)
    times = {
        "before": start - timedelta(milliseconds=1),
        "start": start,
        "inside": start + timedelta(hours=12),
        "end": end,
        "after": end + timedelta(milliseconds=1),
    }
    for name, timestamp in times.items():
        app.server_time = timestamp
        response = app.handle("POST", "/v3/documents", {"title": name, "category": "guide"},
                              {"x-session-key": token})
        assert response.status == 201
    return app


def strong_query(tmp_path):
    raw = yaml.safe_load(DOCUMENTS.read_text())
    checks = raw["steps"][0]["expect"]["response"]
    checks.append({"check": "collection_length", "field": "documents", "op": "==", "value": 3})
    checks.extend({"check": "collection_matching_count", "field": "documents",
                   "matching": {"title": name}, "count": count}
                  for name, count in {"before": 0, "start": 1, "inside": 1, "end": 1, "after": 0}.items())
    path = tmp_path / "known-window.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_public_expiration_example_creates_and_reads_real_record(projections):
    app = ExpiringRecords()
    declaration_before = expansion_view(load_scenario(RECORDS))
    report = run_scenario(RECORDS, record_adapters(app), projections=projections, run_time=BASE)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert report.run_time == BASE
    assert report.run_time_source == "fixed"
    assert report.run_time_values == {"expires_at": "2026-10-31T08:00:00.000Z"}
    assert len(app.requests) == 2
    assert app.requests[0][2] == {"name": report.run_unique, "expires_at": "2026-10-31T08:00:00.000Z"}
    assert app.requests[1][1] == "/items/item-1"
    assert app._items["item-1"] == {"id": "item-1", **app.requests[0][2]}
    assert expansion_view(load_scenario(RECORDS)) == declaration_before
    assert BASE not in repr(report) and report.run_unique not in repr(report)


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["missing", "wrong_time", "null"])
def test_expiration_readback_cannot_pass_with_missing_or_wrong_evidence(projections, fault):
    app = ExpiringRecords(fault)
    report = run_scenario(RECORDS, record_adapters(app), projections=projections, run_time=BASE)
    assert report.status == "FAILED"
    assert all(domain.steps[-1].status == "FAILED" for domain in report.domains)
    assert app._items["item-1"]["expires_at"] == "2026-10-31T08:00:00.000Z"


@pytest.mark.parametrize("projections", PROJECTIONS)
def test_public_recent_query_example_sends_frozen_window(projections):
    app = seeded_documents()
    report = run_scenario(DOCUMENTS, document_adapters(app), projections=projections, run_time=BASE)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert report.run_time_values == {"window_start": "2026-10-23T08:00:00.000Z", "window_end": BASE}
    query = parse_qs(urlsplit(app.requests[-1][1]).query)
    assert query == {"created_from": ["2026-10-23T08:00:00.000Z"],
                     "created_to": [BASE], "cursor": ["0"], "limit": ["20"]}


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("base", [BASE, "2028-03-01T00:00:00.250Z", "2027-01-01T00:00:00.999Z"])
def test_recent_query_checks_known_inside_outside_and_boundaries(tmp_path, projections, base):
    app = seeded_documents(base)
    before = deepcopy((app._documents, app.created_at))
    report = run_scenario(strong_query(tmp_path), document_adapters(app), projections=projections, run_time=base)
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert report.run_time_values["window_start"] == stamp(instant(base) - timedelta(hours=24))
    assert (app._documents, app.created_at) == before


@pytest.mark.parametrize("projections", PROJECTIONS)
@pytest.mark.parametrize("fault", ["ignored_filter", "excluded_boundaries", "empty"])
def test_known_window_checks_detect_filter_faults_that_basic_sample_misses(tmp_path, projections, fault):
    app = seeded_documents(fault=fault)
    # Success plus a page-size check is deliberately insufficient business evidence.
    basic = run_scenario(DOCUMENTS, document_adapters(app), projections=projections, run_time=BASE)
    assert basic.status == "PASSED"
    strong = run_scenario(strong_query(tmp_path), document_adapters(app), projections=projections, run_time=BASE)
    assert strong.status == "FAILED"
    assert all(domain.steps[0].status == "FAILED" for domain in strong.domains)


def test_fixed_time_replays_query_inputs_without_resetting_target_or_unique_values():
    app = seeded_documents()
    first = run_scenario(DOCUMENTS, document_adapters(app), projections=("backend", "contract"), run_time=BASE)
    second = run_scenario(DOCUMENTS, document_adapters(app), projections=("backend", "contract"), run_time=BASE)
    assert first.status == second.status == "PASSED"
    assert app.requests[-1][1] == app.requests[-2][1]
    records = ExpiringRecords()
    runs = [run_scenario(RECORDS, record_adapters(records), projections=("backend",), run_time=BASE)
            for _ in range(2)]
    assert all(report.status == "PASSED" for report in runs)
    assert runs[0].run_time_values == runs[1].run_time_values
    assert runs[0].run_unique != runs[1].run_unique
    assert len(records._items) == 2
