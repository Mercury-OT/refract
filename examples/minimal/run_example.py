"""Run the minimum backend-plus-contract integration with a strict gate."""

from pathlib import Path

from refracto import runner

from examples.minimal.adapters import build_adapters


SCENARIO_PATH = Path(__file__).parent / "scenarios" / "create_and_delete.yaml"


def run():
    adapters = build_adapters()
    rep = runner.run_scenario(
        SCENARIO_PATH,
        adapters,
        projections=("backend", "contract"),
    )
    # Do not gate on rep.passed: it includes DEGRADED.
    assert rep.status == "PASSED"
    assert rep.degradations() == []
    return rep


if __name__ == "__main__":
    run()
