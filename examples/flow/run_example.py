"""Execute the ordered Flow with the existing Documents adapter and target."""
from pathlib import Path

from adapters.documents import build_adapters
from examples.documents.app import DocumentRestApp
from refracto.runner import run_flow


FLOW = Path(__file__).with_name("document_lifecycle.flow.yaml")


def run():
    app = DocumentRestApp()
    report = run_flow(FLOW, build_adapters(app), projections=("backend", "contract"))
    assert report.status == "PASSED", report.localize()
    assert len(app.authentications) == 1
    assert app.request_count == 3
    return report


if __name__ == "__main__":
    result = run()
    print(f"{result.flow_id}: {result.status}")
