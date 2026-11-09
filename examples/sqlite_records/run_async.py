"""Run the bounded observation example against an actual SQLite worker."""

from pathlib import Path
from tempfile import TemporaryDirectory

from adapters.sqlite_records.adapter import build_adapters
from examples.sqlite_records.async_app import AsyncRecordsApp
from refracto.runner import PollConfig, run_scenario


def main():
    scenario = Path(__file__).parent / "scenarios/create_verify_async_delete.yaml"
    with TemporaryDirectory(prefix="refract-async-records-") as directory:
        with AsyncRecordsApp(Path(directory) / "records.sqlite") as app:
            report = run_scenario(scenario, build_adapters(app), projections=("backend",),
                                 poll_config=PollConfig(timeout=2, interval=0.02))
            print(report.status)
            for step in report.domains[0].steps:
                print(step.step_id, step.status)
            return 0 if report.status == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
