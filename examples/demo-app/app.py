"""Self-contained reference application for demonstrating the framework.

This FastAPI app exists only as a public demo target. It keeps the full loop
small and deterministic while still exercising real HTTP, real trace
propagation, and all major projections.
"""
import itertools

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from pydantic import BaseModel

import tracestore

_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(tracestore.InMemorySpanExporter()))
trace.set_tracer_provider(_provider)
_tracer = trace.get_tracer(__name__)

app = FastAPI(title="Refract demo app")
FastAPIInstrumentor().instrument_app(app)

_ITEMS: list[dict] = []
_ID_SEQ = itertools.count(1)
_JOBS: dict[int, dict] = {}
_JOB_SEQ = itertools.count(1)


def reset() -> None:
    """Reset demo application state between runs."""
    global _ID_SEQ, _JOB_SEQ
    _ITEMS.clear()
    _ID_SEQ = itertools.count(1)
    _JOBS.clear()
    _JOB_SEQ = itertools.count(1)


class CreateItemRequest(BaseModel):
    name: str
    rows: list = []


class UpdateItemRequest(BaseModel):
    name: str


class CreateJobRequest(BaseModel):
    rows: list = []


class ArchiveRequest(BaseModel):
    job: int
    note: str = ""


@app.post("/items")
def create_item(body: CreateItemRequest):
    with _tracer.start_as_current_span("item.create") as span:
        span.set_attribute("row_count", len(body.rows))
        item_id = next(_ID_SEQ)
        _ITEMS.append({"id": item_id, "name": body.name, "count": len(body.rows)})
    return {
        "success": True,
        "error": None,
        "data": {"itemId": item_id, "count": len(body.rows)},
    }


@app.put("/items/{item_id}")
def update_item(item_id: int, body: UpdateItemRequest):
    with _tracer.start_as_current_span("item.update") as span:
        for it in _ITEMS:
            if it["id"] == item_id:
                it["name"] = body.name
                span.set_attribute("row_count", it["count"])
                return {
                    "success": True,
                    "error": None,
                    "data": {"itemId": item_id, "count": it["count"]},
                }
        span.set_attribute("row_count", 0)
    return {"success": False, "error": "not found", "data": None}


@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    global _ITEMS
    with _tracer.start_as_current_span("item.delete") as span:
        before = len(_ITEMS)
        _ITEMS = [it for it in _ITEMS if it["id"] != item_id]
        removed = before - len(_ITEMS)
        span.set_attribute("row_count", len(_ITEMS))
    return {
        "success": removed > 0,
        "error": None if removed else "not found",
        "data": {"deleted": removed},
    }


@app.get("/items")
def list_items():
    return {"success": True, "error": None, "data": {"items": list(_ITEMS)}}


@app.get("/debug/traces/{trace_id}")
def get_trace(trace_id: str):
    return {"spans": tracestore.STORE.get(trace_id, [])}


@app.post("/jobs")
def create_job(body: CreateJobRequest):
    with _tracer.start_as_current_span("job.create") as span:
        span.set_attribute("row_count", len(body.rows))
        job_id = next(_JOB_SEQ)
        _JOBS[job_id] = {"rows_count": len(body.rows), "status_polls": 0}
    return {"success": True, "error": None, "data": {"jobId": job_id}}


@app.get("/jobs/{job_id}/status")
def job_status(job_id: int):
    job = _JOBS.get(job_id)
    if job is None:
        return {"success": False, "error": "not found", "data": None}
    job["status_polls"] += 1
    if job["status_polls"] >= 2:
        return {"success": True, "error": None, "data": {"result": "ready"}}
    return {"success": True, "error": None, "data": {}}


@app.get("/jobs/{job_id}/result")
def job_result(job_id: int):
    job = _JOBS.get(job_id)
    if job is None:
        return {"success": False, "error": "not found", "data": None}
    with _tracer.start_as_current_span("job.result.read") as span:
        span.set_attribute("row_count", job["rows_count"])
    return {
        "success": True,
        "error": None,
        "data": {"result": "ready", "count": job["rows_count"]},
    }


@app.post("/archives")
def create_archive(body: ArchiveRequest):
    return {"success": True, "error": None, "data": {"archived": body.job}}


_INDEX_HTML = """<!doctype html>
<html>
<head><title>Refract demo app</title></head>
<body>
  <input data-testid="item-name" type="text" />
  <button data-testid="create-btn">Create</button>
  <ul id="items"></ul>
  <script>
    async function refresh() {
      const res = await fetch('/items');
      const body = await res.json();
      const ul = document.getElementById('items');
      ul.innerHTML = '';
      for (const item of body.data.items) {
        const li = document.createElement('li');
        li.setAttribute('data-testid', 'item-row');
        li.textContent = item.name + ' (' + item.count + ')';
        ul.appendChild(li);
      }
    }
    document.querySelector('[data-testid="create-btn"]').addEventListener('click', async function () {
      var name = document.querySelector('[data-testid="item-name"]').value;
      await fetch('/items', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name, rows: [1, 2, 3]}),
      });
      await refresh();
    });
    refresh();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return _INDEX_HTML
