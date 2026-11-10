"""Run both saved-byte upload consumers: python -m examples.file_upload.run."""

from pathlib import Path

from adapters.file_upload.adapter import build_adapters
from examples.file_upload.server import serve_uploads
from refracto.runner import run_scenario


def main():
    results = []
    with serve_uploads() as (origin, store):
        for product in ("documents", "records"):
            result = run_scenario(Path(__file__).with_name(product + ".yaml"),
                build_adapters(origin, product), projections=("backend", "contract"))
            results.append(result)
            print(f"{result.scenario_id}: {result.status}")
        print(f"HTTP requests: {store.request_count}; saved uploads: {len(store.received)}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
