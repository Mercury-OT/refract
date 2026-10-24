"""Execute the exact time declarations maintained in the public documents."""
from pathlib import Path

import pytest

from refracto.declaration.binding import prepare_step
from refracto.declaration.expansion import expansion_view
from refracto.declaration.loader import load_scenario
from refracto.declaration.run_values import bind_run_values
from tests.test_stabilization_documentation import write_context, yaml_fences


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("document", ["SCENARIO.md", "docs/tasks/run-relative-time.md"])
def test_actual_time_fragment_is_symbolic_and_fixed_replay_resolves_its_window(tmp_path, document):
    fragments = [body for body in yaml_fences((ROOT / document).read_text(encoding="utf-8"))
                 if body.startswith("parameters:\n  expires_at:")]
    assert len(fragments) == 1
    path = write_context(tmp_path, "time_parameters", fragments[0])
    original = load_scenario(path)
    symbolic = expansion_view(original)
    bound, unique = bind_run_values(original, run_time="2026-10-24T08:00:00.000Z")
    assert unique is None
    assert bound.parameters == {
        "expires_at": "2026-10-31T08:00:00.000Z",
        "window_start": "2026-10-23T08:00:00.000Z",
        "window_end": "2026-10-24T08:00:00.000Z",
    }
    prepared, bindings = prepare_step(bound.steps[0], bound, {})
    assert prepared.request.query == {"start": "2026-10-23T08:00:00.000Z",
                                      "end": "2026-10-24T08:00:00.000Z"}
    assert bindings == {}
    assert expansion_view(original) == symbolic
