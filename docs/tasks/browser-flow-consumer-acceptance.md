# Browser Flow consumer: verification and acceptance

Date: 2026-11-02. Starting public main: `522e030`.
Specification: [runnable browser Flow consumer](browser-flow-consumer.md).
Status: development, independent audit, complete regression and architect
acceptance passed. Authorized hosted delivery remains subject to green PR/main
checks and verified cleanup; this record does not claim they have completed.

## Maintainer summary

- One runnable e2e Flow creates, updates and reads a record through a retained page.
- Both existing frontends run the same approved declarations and unchanged target.
- The added mapping reads actual displayed content, without consulting expectations.
- The exercised rendering, persistence and missing-identity faults are detected.
- This adds a consumer example, not a new YAML form, core capability or adoption claim.

## Delivered scope and observed behavior

The [example](../../examples/browser_flow/README.md) contains one Flow, three
Scenarios, their byte-pinned sidecar, the narrow DOM mapping and a strict runner.
The four declaration objects match the approved examples exactly. The three
target sources are byte-identical to the starting commit, with their hashes in
the example's `target-sources.json`; execution verifies them before and after.
Core, browser support, existing adapters, application sources, dependencies and
CI are unchanged.

For descriptive size only, the new adapter is 123 physical lines and runner 87,
including comments and blank lines. The adapter count includes DOM observation,
public browser wiring and bounded diagnostics. This is not a measured reduction
in integration, maintenance or human-review cost.

Promise and native-async implementations each execute eight actual UI actions
and POST/PATCH/GET, with one mapped-user session acquisition, one page navigation
and one context opened and closed. Update and read do not reopen the page; read
uses the record-ID input left by update. Creation publishes the observed ID.
Update publishes the already declared intended name only after a strict pass.
Repeated runs have distinct created IDs, unique codes, sessions and contexts.

The selected projection is live e2e only. Response and DOM checks are separate
observations of the same application, not independent database evidence. The
target's public CRUD endpoints do not enforce authorization: this consumer proves
session continuity, not access-control correctness. The two frontends belong to
one synthetic target, not two unrelated products.

## Failure controls and independent audit

Maintained tests execute isolated faults without editing normal target sources
or approved expectations:

| Fault | Observed result |
| --- | --- |
| Correct HTTP response, incorrect displayed name | Response checks pass; the actual UI count check fails; later nodes are blocked. |
| Correct update acknowledgement, lost persisted update | Create and update pass; actual final GET and DOM retain the old name, so read fails against the declared intended name. |
| Creation response lacks an ID | The presence check fails, no usable ID is published, and no later request guesses an identity. |
| Update is refused | Stop and the explicitly labeled temporary continue variant both invalidate the old expected name; the later read action is blocked. |
| Duplicate actual result element | Observation ERROR before any business request, with later nodes blocked. |
| Nonempty result hidden by CSS | Observation ERROR rather than a substituted empty collection; later nodes are blocked. |

Independent browser probing found one issue before acceptance: `inner_text()`
can be empty for a nonempty element hidden by CSS. The first mapping treated it
as the initial empty display. The Flow still failed, but it lost the distinction
between a business mismatch and unavailable observation. The corrected mapping
uses raw DOM text only to reject that ambiguity; hidden raw content never becomes
visible evidence. Offline and actual-browser regressions cover the correction.

The auditor independently passed 35 dev-only tests and six actual Chromium probes:
normal execution, DOM-only missing identity with correct HTTP, and hidden DOM,
each with both frontends. Missing rendered identity fails the update UI check,
invalidates its publication and prevents GET. All six probes acquire one session
and close one context. The auditor independently confirmed the four approved
declarations, three unchanged source files, safe summary and strict exit gate.
No remaining finding was reported; no repository edits were made by the auditor.

## Reproducible verification

Commands run from the public repository root:

```sh
uv run --locked --no-sync refracto validate-flow examples/browser_flow/browser.flow.yaml
uv run --locked --no-sync refracto validate-flow examples/browser_flow/browser.flow.yaml --expand
uv run --locked --no-sync python -B -m examples.browser_flow.run
uv run --locked --no-sync python -B scripts/run_tests.py --output-dir <new-local-directory> --suite-timeout 240 -- tests/test_browser_flow_consumer.py tests/browser/test_browser_flow_consumer.py -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Validation reports three Scenarios and eight steps. The public entry point runs
both frontends with exit 0. After the observation correction, the focused suite
passes 45 tests: 35 offline and ten actual-browser cases, exit 0 in 14.7 seconds.
Two isolated dev-only environments run the entire offline collection with the
standard guard and a 600-second suite budget: Python 3.11.15 and 3.12.13 each pass
4589 tests, with exit 0, final progress and complete owned-process cleanup.

The existing browser-consumer, retained-context, lifecycle and core litmus
selection passes 66 tests in 61.1 seconds, exit 0 with complete cleanup. The full
unfiltered guarded suite passes 5650 tests in 956.4 seconds, including real
Chromium and Demo tests. It exits 0 with final progress, no diagnostic request,
complete owned-process cleanup and no cleanup errors. One existing Starlette/httpx
dependency warning remains. The full command is:

```sh
uv run --locked --no-sync python -B scripts/run_tests.py --output-dir <new-local-directory> -- -q
```

Lock, hygiene, local documentation links and both diff checks pass. The executable/input
freeze covers 406 unchanged files, with only the three
accepted observation-fix files refreshed before final verification. No private
workspace or product was accessed.

## Delivery boundary

Strict success uses the native report's `status == "PASSED"`. Failure is not
reconstructed into a passing summary, and exception messages, credentials, actual
responses and parameter histories are not automatically printed. Complete native
reports remain available in memory for explicit inspection.

Object absence remains paused. No Flow branch, editor, extra include depth,
automatic cleanup, new assertion or private integration is added. The maintainer
authorized submission after audit and architect acceptance; the PR, required
checks, main checks and branch cleanup must still be verified separately.
