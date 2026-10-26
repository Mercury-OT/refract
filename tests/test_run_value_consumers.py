"""Real stateful public targets, not assertions echoed as generated evidence."""
from copy import deepcopy
from pathlib import Path

import pytest

from refracto.declaration.loader import load_scenario
from refracto.declaration.expansion import expansion_view
from refracto.runner import run_scenario
from tests.test_member_reference_consumers import consumer


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "records": ROOT / "examples/minimal/run_unique_create_locate_read.yaml",
    "documents": ROOT / "examples/documents/scenarios/run_unique_create_locate_read.yaml",
}


@pytest.mark.parametrize("kind", EXAMPLES)
@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_new_runs_on_same_target_locate_the_new_object_not_old_residue(kind, projections):
    # Separate targets per projection configuration; successive runs deliberately
    # keep the same stored objects. The feature itself never isolates storage.
    app, adapters = consumer(kind)
    declaration = load_scenario(EXAMPLES[kind])
    before = deepcopy(expansion_view(declaration))
    reports = [run_scenario(EXAMPLES[kind], adapters, projections=projections) for _ in range(3)]
    tokens = [report.run_unique_values[projections[0]]["run_token"] for report in reports]
    assert len(set(tokens)) == 3
    assert all(type(token) is str and len(token) == 32 for token in tokens)
    assert len(app.requests) == 9
    for index, report in enumerate(reports):
        assert report.status == "PASSED", report.localize()
        assert report.degradations() == []
        assert all(domain.status == "PASSED" for domain in report.domains)
        source, lookup, read = app.requests[index * 3:index * 3 + 3]
        composed = tokens[index] + "-" + kind + "-" + tokens[index]
        assert source[2]["code" if kind == "records" else "title"] == composed
        assert composed in lookup[1]
        expected_id = str(index + 22) if kind == "records" else f"document-{index + 1}"
        assert read[1].endswith("/" + expected_id)
        assert tokens[index] not in repr(report)
    assert expansion_view(declaration) == before
    assert expansion_view(load_scenario(EXAMPLES[kind])) == before


@pytest.mark.parametrize("kind", EXAMPLES)
@pytest.mark.parametrize("fault", ["duplicate", "missing_match", "missing_key", "malformed_row"])
def test_unique_value_does_not_replace_real_selection_evidence(kind, fault):
    app, adapters = consumer(kind, fault)
    report = run_scenario(EXAMPLES[kind], adapters, projections=("backend", "contract"))
    assert report.status != "PASSED"
    assert report.domains[0].steps[-1].status == "BLOCKED"
    assert report.domains[1].status != "PASSED"
    assert len(app.requests) == 2


def test_generated_and_composed_values_are_not_treated_as_server_identifiers():
    app, adapters = consumer("records")
    report = run_scenario(EXAMPLES["records"], adapters, projections=("backend", "contract"))
    assert report.status == "PASSED"
    assert app.requests[-1][1] == "records/22"
    assert report.domains[0].provider_recordings[0].json == {"accepted": True}
    token = report.run_unique_values["backend"]["run_token"]
    assert app.records[22]["code"] == token + "-records-" + token


@pytest.mark.parametrize("kind", EXAMPLES)
def test_backend_and_live_api_share_a_target_without_reusing_created_values(kind):
    app, adapters = consumer(kind)
    report = run_scenario(EXAMPLES[kind], adapters,
                          projections=("backend", "e2e", "contract"))
    assert report.status == "PASSED", report.localize()
    assert report.degradations() == []
    assert len(app.requests) == 6
    generated = report.run_unique_values
    assert generated["backend"] == generated["contract"]
    assert generated["backend"]["run_token"] != generated["e2e"]["run_token"]
    field = "code" if kind == "records" else "title"
    for offset, projection in ((0, "backend"), (3, "e2e")):
        token = generated[projection]["run_token"]
        assert app.requests[offset][2][field] == token + "-" + kind + "-" + token
    assert app.requests[2][1] != app.requests[5][1]
