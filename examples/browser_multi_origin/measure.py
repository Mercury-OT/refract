"""Recompute transparent code counts and compare complete panel outputs."""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import tokenize

from examples.browser_multi_origin.run import CASES


def python_lines(path):
    """Count physical lines touched by Python tokens, including docstrings/data."""
    touched = set()
    ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
               tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}
    for token in tokenize.generate_tokens(io.StringIO(path.read_text()).readline):
        if token.type not in ignored:
            touched.update(range(token.start[0], token.end[0] + 1))
    return len(touched)


def code_counts(repo):
    consumer = repo / "examples" / "browser_multi_origin"
    groups = {
        "product_adapter": [consumer / "adapter.py"],
        "reusable_browser_collection": sorted((repo / "refracto_browser").glob("*.py")),
        "target_application_python": [consumer / "app.py"],
        "measurement_harness": [consumer / "run.py", consumer / "measure.py"],
        "consumer_tests": [repo / "tests" / "browser" / "test_multi_origin_consumer.py"],
    }
    return {"python_token_lines": {name: sum(python_lines(path) for path in paths)
                                    for name, paths in groups.items()},
            "javascript_nonblank_lines": {path.name: sum(bool(line.strip()) for line in path.read_text().splitlines())
                                           for path in sorted(consumer.glob("*.js"))},
            "yaml_nonblank_lines": sum(bool(line.strip()) for path in (consumer / "scenarios").glob("*.yaml")
                                       for line in path.read_text().splitlines()),
            "mapping_entries": {"element_targets": 14, "page_targets": 1, "api_endpoints": 1,
                                "static_origins": 1, "credential_origins": 1},
            "maintenance_configuration_fields": ["selector_prefix", "api_prefix"]}


def validate_panel(panel):
    rows = panel["records"]
    expected = {(implementation, case) for implementation in ("promise", "async") for case in CASES}
    identities = [(row["implementation"], row["case_id"]) for row in rows]
    if len(identities) != len(expected) or set(identities) != expected:
        raise ValueError("panel omitted or duplicated an execution unit")
    if panel["expected_units"] != len(expected) or panel["executed_units"] != len(rows):
        raise ValueError("panel count mismatch")
    counts = dict(Counter(row["status"] for row in rows))
    if counts != panel["status_counts"]:
        raise ValueError("status count mismatch")
    return {identity: row for identity, row in zip(identities, rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--maintenance", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, action="append", default=[],
                        help="additional complete candidate panel for descriptive stability checks")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panels = {name: json.loads(getattr(args, name).read_text()) for name in ("baseline", "candidate", "maintenance")}
    panels.update({f"candidate_repeat_{index}": json.loads(path.read_text())
                   for index, path in enumerate(args.repeat, 1)})
    indexed = {name: validate_panel(panel) for name, panel in panels.items()}
    for identity in indexed["baseline"]:
        if len({rows[identity]["scenario_sha256"] for rows in indexed.values()}) != 1:
            raise ValueError("business Scenario changed between measurements")
    result = {"measurement_version": 1, "code_counts": code_counts(Path(__file__).resolve().parents[2]),
              "panels": {name: {key: panel[key] for key in ("expected_units", "executed_units", "status_counts", "elapsed_seconds", "human_effort")}
                         for name, panel in panels.items()},
              "scenario_hashes_unchanged": True,
              "limits": ["Synthetic capability evidence, not adoption or measured human savings.",
                         "Native async gaps stay in the denominator.",
                         "A fixed configuration change is not a measured general maintenance rate."]}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
