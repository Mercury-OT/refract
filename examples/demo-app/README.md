# Demo App

This directory contains the self-contained reference application used to explain
and validate the framework.

## Purpose

The demo app exists to provide a public target that exercises the framework end
to end without relying on a private product, external infrastructure, or
network-only services.

It is intentionally small, but it is not a toy placeholder. It demonstrates:

* backend projection against real HTTP endpoints
* frontend projection against a runnable UI
* e2e projection with trace propagation
* contract projection against recorded provider behavior
* state observation through a trace-backed debug endpoint

## Run

From this directory:

```bash
python run.py --host 127.0.0.1 --port 8765
```

## Structure

* `app.py` — FastAPI demo application
* `tracestore.py` — in-memory span store used by the debug trace endpoint
* `run.py` — minimal uvicorn launcher
