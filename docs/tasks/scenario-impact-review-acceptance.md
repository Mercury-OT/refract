# Shared Scenario change-impact review: local acceptance

## Decision

**PASS**, following specification, development, independent audit and architect
verification on 2026-10-16. The [specification](scenario-impact-review.md) defines
the accepted scope. This is local engineering acceptance, not submission,
business acceptance, human approval of any changed Scenario, or evidence of
reduced review effort.

The preceding reuse walkthrough was separately submitted through PR #17 and
merged as `967af3c4f96a8b5ebbf1e12f624aa1b789698b2b`. Its eight branch/PR checks
and four post-merge main jobs passed, and both task branches were removed before
this implementation began. That submission authorization does not extend to
this task. This task's starting and ending HEAD is that same commit, equal to
local `origin/main` and the checked remote main. Its changes remain unstaged,
uncommitted and unpushed. Private workspaces and products were not accessed.

## Delivered behavior

`refracto impact` compares explicitly supplied old/current child files and scans
an explicitly selected Scenario directory. It reports structural changes,
callers of the exact child file, argument/default wiring, named-result consumers,
and actual fingerprint state. It does not infer callers from an equal Scenario
ID in a different file.

Actual declaration validity is separate from hypothetical loads using the
current parent and current other dependencies with the selected old/new child.
A removed consumed result is a known incompatibility. Missing or unknown
evidence makes inspection incomplete. Neither case updates a pin or runs a
Scenario. Comments and formatting still affect the byte fingerprint.

Default reports hide authored literal values, but visible identifiers and paths
can still be confidential. Explicit `--show-values` is a source-confidentiality
view, not a runtime-value dump. The command does not write files or access Git,
network, subprocesses, adapters, or execution services.

Current YAML, one-level inclusion, same-actor rules, and runtime fingerprint
enforcement are unchanged. No loader, model, vocabulary, execution projection,
adapter, dependency, lock, or CI changes were needed.

## Independent findings and resolution

The auditor confirmed one blocker: recursive directory traversal could exceed
Python's recursion limit while still inside the permitted entry budget, raising
an exception instead of producing an inspection result. Development replaced
traversal with an iterative implementation. The original independent probe and
an added regression using 140 actual nested directories both pass; no new
depth restriction was introduced.

The independent review additionally tested consumed-result removal, multiple
include sites, stale actual pins, same-ID/different-file exclusion, nested strict
scalar comparison, reference-shaped literal data, escaped consumer locations,
unknown pins, unrelated malformed inputs, confidentiality, read-once capture,
malformed parents, ignored-directory inspection and non-regular inputs.
No unresolved blocking finding remains. The auditor did not modify repository
files. Developer and auditor were separate agents from the accepting architect.

## Observed verification

Commands ran from the public repository using its existing locked environment.

| Check | Actual result |
| --- | --- |
| Developer: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/test_scenario_impact.py tests/test_include_cli.py` | **72 passed**: 65 new tests and 7 existing CLI tests, 0.50 seconds. |
| Independent audit: those suites plus separate synthetic counterexamples | **90 passed**: the 72 repository checks and 18 additional independent probes, 0.56 seconds. |
| Architect: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q` | **1217 passed**, no skips, one existing Starlette/httpx deprecation warning, 138.15 seconds. Includes existing real Demo/browser checks. |
| Architect: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/test_opensource_litmus.py` | **3 passed**, 0.09 seconds. |
| `uv lock --check`; `bash scripts/check_repository_hygiene.sh`; tracked diff and cached diff checks | Passed; index empty. New files were separately inspected for information-source neutrality and whitespace. |
| Read-only smoke against `examples/scenario-reuse`, with identical child inputs | COMPLETE, exit 0, correct caller, parameter wiring and named-result consumer. |
| Read-only comparison of review-exercise baseline child and case-03 child, with case-03 as caller scope | COMPLETE, exit 1; correctly reports the removed backend-state assertion and all three `record_id` uses. Both hypothetical declarations remain valid, without interpreting the removal as approved. |

An earlier full run passed 1216 tests before the traversal regression was added;
the 1217-test run above is the final result on the repaired implementation.
Early developer test-fixture/help-wrapping failures and the audit traversal
failure were corrected and rerun, not counted as successful verification.

## Accepted file scope

Exactly eight public files:

- `refracto/declaration/impact.py`.
- `refracto/cli.py`.
- `tests/test_scenario_impact.py`.
- `docs/impact-review.md`.
- `docs/tasks/scenario-impact-review.md`.
- `docs/tasks/scenario-impact-review-acceptance.md`.
- `SCENARIO.md`: only the review-guide link, no YAML contract change.
- `docs/roadmap.md`: prior submission facts and current local acceptance status.

Sources are the public declaration implementation, published neutral examples,
the approved bounded review-tool requirement and independently constructed
synthetic fixtures. No private product code, paths, evidence, credentials or
personal measurements are included. MANIFESTO, BRAND, prior Scenario sources,
sidecars and historical acceptance records are unchanged.

## Remaining boundaries

Inspection is bounded by the selected directory and documented resource limits.
Captured bytes are reused within one inspection; this is not an atomic
filesystem snapshot or protection against a malicious concurrent writer.
Hypothetical checks are not historical replay. The tool does not prove semantic
equivalence, approval quality, complete business coverage, or human time savings.

No new nesting, review UI, approval platform, automatic pin update or private
product migration follows from this acceptance. Submission remains a separate
maintainer-authorized task; no staging, commit, push or PR was performed for
these eight files.
