# Bounded test execution: verification record

Date: 2026-11-01. Starting main: `101585b`.
Specification: [bounded test execution and stall diagnostics](test-execution-guard.md).
Status: development, independent implementation/CI reviews and architect
acceptance passed. Final frozen-source regression passed all 5457 tests with
real Chromium, no skips and one existing dependency warning.
Hosted delivery must separately satisfy the authorized PR, main CI and cleanup
gates; this record does not claim those have already completed.

## Maintainer summary

- Repository tests retain their active test and phase, output and available stacks.
- An external deadline bounds stalls, including teardown and process shutdown.
- Ordinary failures remain failures; there are no automatic retries or exclusions.
- Cleanup considers only the owned process group and reports uncertainty honestly.
- Scenario, production behavior, dependencies and private workspaces are unchanged.

## Implementation and scope

The standard-library launcher starts the current interpreter's pytest in a new
POSIX session. Its explicitly loaded progress plugin is repository test tooling,
not part of a Scenario or product adapter. A one-shot bootstrap prevents nested
pytest runs from taking ownership of the outer record. Output goes to regular
files, so descendant output handles cannot hold a supervisor pipe open.

Defaults are a 120-second diagnostic request, a 300-second unchanged-phase stop
and a 2700-second whole-suite ceiling. Cleanup adds the documented bounded
diagnostic/TERM/KILL/inspection grace. These are test-infrastructure budgets;
no product timeout is changed. CLI errors fail before launch, pytest's ordinary
exit codes are preserved, and timeout, invalid progress, incomplete cleanup or
interruption cannot yield success. There is no automatic rerun-to-green.

CI retains both core Python versions, the litmus checks, the unfiltered full
suite, demo extra, real Chromium and existing required job names. Core and full
job ceilings are twenty and sixty minutes. Artifact upload is attempted after
success or failure with seven-day retention. The CI sentinel rejects filtering,
unguarded execution, missing browser installation and weakened retention.

## Findings and corrections

Independent review found three defects before broad regression:

1. The synthetic test harness derived cleanup ownership from deliberately
   corrupted progress. It now uses an exclusively created, parent-only marker.
2. A FIFO replacing progress.json could block the supervisor beyond its deadline.
   Nonblocking descriptor reads now verify a regular file before reading.
3. A FIFO at a predictable result.tmp path could block final result writing.
   Final output now uses an exclusively created unique regular temporary file.

The first broad Python 3.12 core run then reported two cleanup failures:
4402 passed, two failed, one expected collection skip. The original result and
control records were retained. The then-running browser regression was explicitly
interrupted after 332.66 seconds, with exit 143, a captured stack and complete
owned-group cleanup. That interrupted run is neither a pass nor a product failure.

The developer reproduced the cause in twenty of twenty owned processes: on
macOS, signal-zero probing of an exited, unreaped zombie group returned EPERM.
The independent reviewer separately confirmed it five of five times, checking
the zombie state before probing. Cleanup had allowed this exception to escape
and had discarded its partial action record. The correction uses bounded process
inspection to distinguish zombie-only groups from live inaccessible members,
continues bounded escalation after signal errors, and preserves sent signals
and sanitized operation/exception-type/errno diagnostics. Unknown inspection is
reported as group_inspection_failed, never as observed surviving processes or
successful cleanup. Live inaccessible members still fail.

A focused run exposed a test-only stale-progress race: truncate/write could
produce invalid JSON before the intended sequence rollback. The control now
publishes atomically and waits for explicit supervisor observation. Child signal
readiness likewise uses a marker after handler installation, not a fixed sleep.
No deadline or assertion was relaxed. Intermediate failures remain recorded;
the final checks below use the corrected frozen files.

## Independent verification

The final implementation reviewer passed all 51 real-subprocess controls in
30.15 seconds. Its guard exited 0 after 30.364 seconds with valid final progress,
complete cleanup and no cleanup errors. Diagnostic/phase/suite budgets were
10/30/90 seconds with an independent 110-second outer deadline.

Controls cover each stalled phase, native blocking, missing readiness, invalid
or stale records, nested pytest, parameter privacy, TERM-resistant processes,
owned versus unrelated processes, escaped-session limitations, both FIFO cases,
zombie-only groups, inaccessible live members, unknown inspection and preservation
of successful TERM evidence when KILL fails. The stale-sequence observation
marker is published atomically; child readiness is checked after handler installation.

Eight additional subprocess probes on the earlier independently audited revision
also checked both FIFO cases, non-daemon shutdown, initial conftest import,
native os.read, a TERM-resistant pytest, interruption before readiness and an
oversized progress record. Their six-second outer deadlines held; they are not
substituted for the final corrected 51-control run or broad regressions.

A separate reviewer checked CI, documentation, unchanged production files and
public sources. No unresolved implementation or CI/documentation finding remains.
This audit does not identify the cause of the earlier PR #45 main CI stall.

## Commands and results

Commands run from the public checkout. Core environments contain only the dev
extra, with no Playwright, FastAPI or HTTPX. Output directories are new per run.
All completed final guarded pytest commands below exited 0 with valid final progress and
complete owned-group cleanup.

| Command / environment | Actual result |
| --- | --- |
| `python scripts/run_tests.py --output-dir OUTPUT --diagnostic-after 10 --phase-timeout 30 --suite-timeout 90 -- -q -o addopts= tests/test_test_execution_guard.py` | Developer: 51 passed, 30.48 seconds; independent reviewer: 51 passed, 30.15 seconds |
| Dev-only Python 3.11.15: `python scripts/run_tests.py --output-dir OUTPUT --suite-timeout 600 -- -q -o addopts=` | 4408 passed, one expected optional-dependency collection skip, 41.97 seconds |
| Dev-only Python 3.12.13: same guarded core command | 4408 passed, one expected optional-dependency collection skip, 41.88 seconds |
| Each dev-only version: `python scripts/run_tests.py --output-dir OUTPUT --suite-timeout 120 -- tests/test_opensource_litmus.py -q` | Three passed per version |
| `uv run --locked --no-sync python scripts/run_tests.py --output-dir OUTPUT -- -q -o addopts=` | Final full/browser run: 5457 passed, one existing Starlette/httpx warning, no skips, 929.49 seconds; launcher exit 0 after 929.84 seconds |
| `uv lock --check`, repository hygiene, diff/cached-diff checks | Passed |

## Frozen sources and accepted file boundary

The final independently audited SHA-256 values are:

- scripts/run_tests.py: `20c1326358f3bdda667a8740bcdcf78dd91acda760a4ab596130aa1178fa3d37`.
- scripts/_refract_test_guard.py: `083e76adb8b5b44472f455f3555141a349a14a3deba80059f8156cb116dea3ff`.
- tests/test_test_execution_guard.py: `c9ecfc81fa2433e34e4bf98851c03e411ffdfce823d0731559728aedc78cecac`.

Submission hygiene then identified two synthetic source strings whose escaped
newline adjacent to a pytest decorator resembled an email address to the existing
scanner. Splitting adjacent string literals fixes that false positive without
changing their contents or the hygiene policy. Exact pre/post Python AST equality
was verified; the publication-form test hash is
`a01a291dec6b91a99d62776ee834612ef3fdb4364844dee53634837984e91fbf`.
Launcher and plugin hashes remain identical to all final executed checks above.

The ten-file scope comprises the CI workflow, README, roadmap, this record and
its specification, docs/testing.md, the two launcher/plugin scripts, the new
guard tests and the existing CI-coverage sentinel. Of 481 starting tracked files,
477 remain byte-identical; only the four authorized existing files change.
Core, browser helper, adapters, Scenario files, declarations, vocabulary,
dependencies, lock and brand/manifesto files are untouched.

All new material comes from public repository behavior, public CI history and
neutral synthetic subprocess controls. No private sources, private-product details,
credentials or private-workspace evidence is used. No private workspace was accessed.
The later associated PR and exact main CI establish publication, not this local
verification record or source fingerprints alone.

## Limits and next decision

Linux/macOS process groups are not a sandbox. Descendants creating a new session
can escape cleanup; a dead host or uninterruptible kernel/filesystem work can
prevent a final record. Raw pytest logs and stack paths are not generally redacted.
CI's disposable worker and job ceiling remain separate boundaries.

The former unexplained CI stall remains unexplained. This task improves future
diagnosis and bounded failure; it does not claim that cause was repaired. After
authorized delivery, return only to the bounded Flow design assessment. No Flow
format, deeper include, UI or object-absence capability is introduced here.
