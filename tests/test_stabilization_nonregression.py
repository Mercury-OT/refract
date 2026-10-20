"""Live regression obligations, separate from immutable historical measurements."""
import pytest

from tests import stabilization_controls as controls


@pytest.mark.parametrize("row", [row for row in controls.ROWS if row.startswith("F")])
def test_previously_detected_synthetic_fault_must_remain_detected(row):
    neighbor = controls.observe(row, False)
    injected = controls.observe(row, True)
    # A missed fault is a legitimate experiment observation, but not an
    # acceptable regression for a detector already established by this panel.
    assert controls.classify(row, injected, neighbor) == "detected"
