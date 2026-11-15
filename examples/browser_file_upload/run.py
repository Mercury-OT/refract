"""Run the authored upload consumers: python -m examples.browser_file_upload.run."""
import argparse
import hashlib
import json
from pathlib import Path

from adapters.browser_file_upload.adapter import build_adapters
from examples.browser_file_upload.app import application
from refracto.ports import MockResponse
from refracto.runner import run_scenario


ROOT = Path(__file__).resolve().parent
TARGET_FILES = ("app.py", "documents.html", "documents.js", "records.html", "records.js")


def target_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in TARGET_FILES}


def verify_frozen_targets():
    expected = json.loads((ROOT / "target-sources.json").read_text())["sha256"]
    if target_hashes() != expected:
        raise ValueError("synthetic upload target differs from its frozen baseline")


def mock_plan(product):
    if product not in {"documents", "records"}:
        raise ValueError("unknown upload consumer")
    source = product + "-mock.json"
    return [MockResponse(fixture_id=product + "-upload", source=source,
        method="POST", path="documents" if product == "documents" else "records/archive/attachments",
        status=201, response=json.loads((ROOT / source).read_text()))]


def execute(app, product, *, projections=("e2e",), scenario_path=None):
    verify_frozen_targets()
    if projections == ("frontend",):
        source = ROOT / (product + "-frontend.yaml")
    else:
        source = ROOT / (product + ".yaml")
    bundle = build_adapters(app.base_url, product)
    try:
        report = run_scenario(scenario_path or source, bundle, projections=projections,
            mock_plan=mock_plan(product) if projections == ("frontend",) else None)
        return report, bundle
    finally:
        verify_frozen_targets()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", choices=("documents", "records", "both"), default="both")
    parser.add_argument("--projection", choices=("e2e", "frontend", "backend-contract", "all"), default="all")
    args = parser.parse_args()
    products = ("documents", "records") if args.product == "both" else (args.product,)
    scopes = (("e2e",), ("frontend",), ("backend", "contract")) if args.projection == "all" else (
        (("backend", "contract"),) if args.projection == "backend-contract" else ((args.projection,),))
    passed = True
    for product in products:
        for projections in scopes:
            with application() as app:
                report, bundle = execute(app, product, projections=projections)
                row = {"product": product, "projections": projections, "status": report.status,
                    "steps": [{"id": step.step_id, "status": step.status}
                              for domain in report.domains for step in domain.steps],
                    "browser_contexts_opened": bundle.ui.opened_contexts,
                    "browser_contexts_closed": bundle.ui.closed_contexts,
                    "api_calls": len(bundle.api.calls), "server_uploads": len(app.store.received)}
            row["server_closed"] = app.closed
            print(json.dumps(row, sort_keys=True))
            passed = passed and report.passed and app.closed
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
