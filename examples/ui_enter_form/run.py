"""Run the unchanged Enter Scenario and adapter on two native form variants."""
import argparse
import hashlib
import json
from pathlib import Path

from examples.ui_enter_form.app import Application
from examples.ui_enter_search.run import SCENARIO, run_case as run_search_case


ROOT = Path(__file__).resolve().parent
TARGET_FILES = ("app.py", "listener.js", "property.js")
SHARED_FILES = ("../ui_enter_search/app.py",)


def target_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in TARGET_FILES + SHARED_FILES}


def verify_frozen_targets():
    manifest = json.loads((ROOT / "target-sources.json").read_text())
    expected = {**manifest["sha256"], **manifest["shared_sha256"]}
    if target_hashes() != expected:
        raise ValueError("synthetic form target source differs from its frozen baseline")


def run_case(implementation, *, app_type=Application, timeout_ms=5000):
    verify_frozen_targets()
    row = run_search_case(implementation, app_type=app_type, timeout_ms=timeout_ms)
    row["reused_search_target_sha256"] = row.pop("target_sha256")
    row["target_sha256"] = target_hashes()
    row["scenario_source"] = "examples/ui_enter_search/scenario.yaml"
    row["adapter_source"] = "examples/ui_enter_search/adapter.py"
    verify_frozen_targets()
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", choices=("listener", "property", "both"), default="both")
    args = parser.parse_args()
    names = ("listener", "property") if args.implementation == "both" else (args.implementation,)
    rows = [run_case(name) for name in names]
    print(json.dumps({"consumer_version": 1, "runs": rows}, indent=2, sort_keys=True))
    return 0 if all(row["status"] == "PASSED" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
