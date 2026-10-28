"""Run the public example with a temporary local database and clean it up."""

from pathlib import Path
from tempfile import TemporaryDirectory

from adapters.sqlite_records.adapter import build_adapters
from examples.sqlite_records.app import RecordsApp
from refracto.runner import run_scenario


def main():
    scenario = Path(__file__).parent / "scenarios/create_and_verify_storage.yaml"
    with TemporaryDirectory(prefix="refract-records-") as directory:
        with RecordsApp(Path(directory) / "records.sqlite") as app:
            report = run_scenario(scenario, build_adapters(app), projections=("backend",))
            print(report.status)
            for step in report.domains[0].steps:
                print(step.step_id, step.status)
            return 0 if report.status == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
