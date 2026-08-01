"""Standalone, offline tests for the self-contained demo app (examples/demo-app/).

These tests exercise the FastAPI app in-process via TestClient — no adapter,
no core involved. They prove:
  1. A manually emitted semantic span (`item.create`, attr `row_count`) is
     captured by the in-memory trace store.
  2. That span lands under the trace_id from the inbound `traceparent` header
     (i.e. FastAPI's OTel auto-instrumentation respects the caller-supplied
     trace context rather than minting its own).
  3. GET /items reflects newly created entries.
"""
import secrets
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # skip cleanly (not abort collection) if demo extra isn't installed

DEMO_APP_DIR = Path(__file__).resolve().parent.parent / "examples" / "demo-app"
if str(DEMO_APP_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_APP_DIR))

from fastapi.testclient import TestClient  # noqa: E402

import app as demo_app_module  # noqa: E402
import tracestore  # noqa: E402


def gen_traceparent() -> tuple[str, str]:
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    return f"00-{trace_id}-{span_id}-01", trace_id


@pytest.fixture(autouse=True)
def _reset_store():
    tracestore.reset()
    demo_app_module.reset()
    yield
    tracestore.reset()
    demo_app_module.reset()


@pytest.fixture
def client():
    return TestClient(demo_app_module.app)


def test_post_items_emits_item_create_span_under_inbound_trace_id(client):
    traceparent, trace_id = gen_traceparent()
    rows = [{"a": 1}, {"a": 2}, {"a": 3}]

    resp = client.post(
        "/items",
        json={"name": "widgets", "rows": rows},
        headers={"traceparent": traceparent},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["count"] == len(rows)
    assert "itemId" in body["data"]

    debug_resp = client.get(f"/debug/traces/{trace_id}")
    assert debug_resp.status_code == 200
    spans = debug_resp.json()["spans"]

    item_create_spans = [s for s in spans if s["name"] == "item.create"]
    assert len(item_create_spans) == 1, f"expected exactly one item.create span, got: {spans}"
    assert item_create_spans[0]["attributes"]["row_count"] == len(rows)


def test_get_items_reflects_created_entry(client):
    traceparent, _ = gen_traceparent()
    resp = client.post(
        "/items",
        json={"name": "gadgets", "rows": [{"x": 1}]},
        headers={"traceparent": traceparent},
    )
    assert resp.status_code == 200
    item_id = resp.json()["data"]["itemId"]

    list_resp = client.get("/items")
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert items == [
        {"id": item_id, "name": "gadgets", "count": 1}
    ], f"created item not reflected in list: {items}"


def test_debug_traces_unknown_trace_id_returns_empty_list(client):
    resp = client.get("/debug/traces/" + "0" * 32)
    assert resp.status_code == 200
    assert resp.json() == {"spans": []}


def test_post_jobs_emits_job_create_span_under_inbound_trace_id(client):
    traceparent, trace_id = gen_traceparent()
    rows = [{"a": 1}, {"a": 2}]

    resp = client.post(
        "/jobs",
        json={"rows": rows},
        headers={"traceparent": traceparent},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["error"] is None
    assert "jobId" in body["data"]

    debug_resp = client.get(f"/debug/traces/{trace_id}")
    assert debug_resp.status_code == 200
    spans = debug_resp.json()["spans"]

    job_create_spans = [s for s in spans if s["name"] == "job.create"]
    assert len(job_create_spans) == 1, f"expected exactly one job.create span, got: {spans}"
    assert job_create_spans[0]["attributes"]["row_count"] == len(rows)


def test_job_status_ready_by_poll_count(client):
    traceparent, _ = gen_traceparent()
    create_resp = client.post(
        "/jobs",
        json={"rows": [{"a": 1}]},
        headers={"traceparent": traceparent},
    )
    job_id = create_resp.json()["data"]["jobId"]

    first = client.get(f"/jobs/{job_id}/status")
    assert first.status_code == 200
    first_data = first.json()["data"]
    assert "result" not in first_data, f"1st poll should be pending, got: {first_data}"

    second = client.get(f"/jobs/{job_id}/status")
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data.get("result") == "ready", f"2nd poll should be ready, got: {second_data}"


def test_job_result_emits_job_result_read_span_and_not_job_compute(client):
    traceparent, trace_id = gen_traceparent()
    create_resp = client.post(
        "/jobs",
        json={"rows": [{"a": 1}, {"a": 2}, {"a": 3}]},
        headers={"traceparent": traceparent},
    )
    job_id = create_resp.json()["data"]["jobId"]

    # drive to ready
    client.get(f"/jobs/{job_id}/status")
    client.get(f"/jobs/{job_id}/status")

    result_traceparent, result_trace_id = gen_traceparent()
    result_resp = client.get(
        f"/jobs/{job_id}/result",
        headers={"traceparent": result_traceparent},
    )
    assert result_resp.status_code == 200
    body = result_resp.json()
    assert body["success"] is True
    assert body["data"]["result"] == "ready"
    assert body["data"]["count"] == 3

    debug_resp = client.get(f"/debug/traces/{result_trace_id}")
    spans = debug_resp.json()["spans"]

    job_result_read_spans = [s for s in spans if s["name"] == "job.result.read"]
    assert len(job_result_read_spans) == 1, f"expected exactly one job.result.read span, got: {spans}"

    job_compute_spans = [s for s in spans if s["name"] == "job.compute"]
    assert len(job_compute_spans) == 0, (
        f"job.compute must NOT be emitted here (async-worker span correlation is future), got: {spans}"
    )


def test_post_archives_echoes_archived_job_id(client):
    traceparent, _ = gen_traceparent()
    create_resp = client.post(
        "/jobs",
        json={"rows": [{"a": 1}]},
        headers={"traceparent": traceparent},
    )
    job_id = create_resp.json()["data"]["jobId"]

    resp = client.post("/archives", json={"job": job_id, "note": "archived"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["archived"] == job_id
