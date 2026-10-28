# Mapping fidelity: bounded verification results

## Scope and evidence

Local architect acceptance **PASS**, 2026-10-28, against starting main `ee4691e` and the
[approved specification](mapping-fidelity.md). The maintainer authorized public
submission after independent audit and architect acceptance; hosted PR/main
checks and cleanup remain separate publication gates.

This exercise adds tests, not execution capabilities. The unchanged Documents
create/read Scenario runs against the existing stateful **in-process** target,
with backend only. There is no HTTP-network, browser or private-product pilot
in this panel. No assertion, YAML, production adapter, core or dependency change
is required. The test file contains all samples and fault wrappers; no generic
mapping specification or fault framework is introduced.

## Observed panel

The 13 collected tests cover four fault classes plus their normal controls.
The table separates Scenario execution from the test's independent mapping
comparison; the latter is not a new RunReport field or automatic runtime gate.

| Control | Scenario result | Separate mapping comparison / explanation |
| --- | --- | --- |
| Normal create/read | PASSED | Actual route and observed fields agree with the selected mapping contract. |
| M1: resolver reads another existing object | FAILED | `read` fails `field_equals` for `document_id` and `title`. Actual GET and raw returned ID identify the unrelated object; the route comparison also fails. Both objects were really created under the same account; this is not a 404 control. |
| M2: target read returns a changed title; honest normalizer | FAILED | `read.title` fails; mapping remains faithful to the changed observation. |
| M2: changed target title **plus** stale normalizer | **PASSED** | Mapping comparison fails: the actual call returns the old normalized title while raw evidence contains the changed title. This is a combined target/adapter fault, not a core detection. |
| M3: target read omits title; honest normalizer | FAILED | `read.title` fails; the mapper faithfully preserves absence. |
| M3: missing target title **plus** fabricated title | **PASSED** | Mapping comparison fails: the returned fields invent a title absent from the actual response. This is a combined target/adapter fault. |
| M4: same changed response, only the read-title assertion removed | Strong FAILED; weak **PASSED** | Raw and normalized observations are identical across the two runs. The difference is the missing obligation, not adapter fidelity. Only a temporary Scenario copy is weakened. |

M2 and M3 also fail independent fixed two-response sample comparisons without
any Scenario execution. Literal expected fields are written explicitly in the
test, not derived from the tested normalizer or a passing report. Runtime
comparisons use the actual normalization call's captured input and output, not a
second call. Checks preserve status, raw response and request snapshots and
confirm injection counts. M1's route expectation uses the actual create-response
ID and the independently specified Documents route, not the resolver's output.

## Reproduction and existing coverage

From the repository root:

```sh
uv run --frozen pytest -o addopts='' -q tests/test_mapping_fidelity.py
```

Result: **13 passed**, exit 0. The same 13 tests also pass with only the dev
extra installed; no optional browser dependency is needed.

The exact new test groups are:

- `test_literal_samples_define_the_normal_mapping` (original, changed, missing).
- `test_fixed_response_sequence_detects_mapping_fault_without_a_scenario`
  (M2-stale, M3-invented).
- `test_resolver_object_mapping_is_checked_against_real_created_identity`
  (normal, M1-wrong-object).
- `test_real_run_keeps_scenario_and_mapping_outcomes_separate`
  (normal, M2-target-only, M2-combined, M3-target-only, M3-combined).
- `test_M4_omitted_title_obligation_passes_identical_faulty_observations`.

Existing tests are reused, not counted as newly supplied coverage:

```sh
uv run --frozen pytest -o addopts='' -q \
  tests/test_member_reference_consumers.py \
  tests/test_field_comparison_consumers.py tests/test_rejection_evidence.py \
  tests/test_header_documents.py tests/test_query_documents.py \
  tests/test_stabilization_measurements.py tests/test_stabilization_nonregression.py \
  tests/test_action_port_boundary.py
```

Result: **331 passed**, exit 0. They already cover selected IDs, complete content
and types, raw rejection reasons, weak/strong checks, actual idempotency effects,
query evidence, frozen counterexamples and action-port ownership. The historical
stabilization measurements and fixtures are unchanged.

## Independent audit and regression

An independent reviewer passed the implementation and evidence audit. It reran
all 13 tests in the full environment and in Python 3.11/3.12 dev-only installs.
Six additional in-memory reverse probes were rejected: wrong sample title,
wrong title mapping during normal execution, wrong real-object route, disabled
M2 injection, disabled M3 injection, and raw-evidence mutation. The reviewer
confirmed oracle independence, actual fault reachability, separate outcomes,
the one-assertion temporary edit, and public-source boundaries.

| Check | Actual result (exit 0) |
| --- | --- |
| `uv run --frozen pytest -o addopts='' -q` | 4319 passed; one existing third-party deprecation warning. |
| `python -m pytest -o addopts='' -q` in dev-only Python 3.11.15 and 3.12.13 installs | 3742 passed, 1 skipped in each. Optional browser/demo dependencies are absent. |
| `uv run --frozen pytest -o addopts='' -q tests/test_opensource_litmus.py tests/test_stabilization_documentation.py tests/test_stabilization_boundaries.py` | 90 passed. |
| `uv lock --check` | Passed. |
| `bash scripts/check_repository_hygiene.sh` | Passed; separate source review confirms neutral synthetic examples. |
| `git diff --check` and `git diff --cached --check` | Passed. |
| Starting tracked-file SHA-256 comparison | 375 of 377 files unchanged. Only roadmap and threat-model links changed; three task files were added. Core, production adapters, examples, all existing YAML/pins, dependencies, CI and historical evidence are byte-identical. |

Accepted scope is exactly the new specification, this acceptance record,
`tests/test_mapping_fidelity.py`, `docs/roadmap.md`, and `docs/threat-model.md`.
At local acceptance, the publication gates were still to run. The authorized task
PR records hosted CI and merge evidence; local test success alone is not a
claim that those gates passed. No private workspace was accessed.

## Limits and stop decision

The useful result is a reproducible distinction: an honest mapper can expose a
bad observation, a faulty mapper can conceal it, and a missing assertion can
leave it unchecked. No universal mapping guarantee follows from these samples.
The scope does not defend against hostile same-process Python, certify an
adapter for unseen inputs, or measure review cost, real adoption or product
quality. Contract would share relevant sources and is not counted as independent
evidence. See the [threat model](../threat-model.md).

No general conformance platform or core fix is justified by this fixed panel.
Stop at this evidence. Future mapping samples should follow an actual integration
need rather than turn this exercise into another mandatory hardening campaign.
Database evidence remains paused; Flow remains a separate design decision.
