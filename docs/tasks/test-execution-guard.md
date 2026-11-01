# Bounded test execution and stall diagnostics

Date: 2026-11-01. Baseline: public main `101585b`.
Status: maintainer authorized this bounded specification, development,
independent audit and architect acceptance, followed by public submission after
acceptance. This is test infrastructure, not a Scenario or runtime feature.

## Problem and claim

The first main CI attempt for PR #45 stopped producing progress after 9% for
more than twenty minutes. It was cancelled with its log retained; the same
commit passed on a second attempt. Neither observation identifies the active
test or proves a root cause. Do not label this task a fix for that unknown cause.

Make future stalled test executions identifiable and bounded: retain the active
test/phase, request Python stack diagnostics, and exit unsuccessfully within an
external execution budget. Ordinary successful and failing pytest results retain
their meaning. No retries, exclusions or assertion changes make a run pass.

## Authorized scope and invariants

- Add a repository-only Python test launcher and an explicitly loaded pytest
  plugin under `scripts/`, plus synthetic subprocess controls under `tests/`.
- Adopt that launcher in public CI, with a job ceiling and retained diagnostics;
  update the existing CI-coverage sentinel to recognize the new full-suite entry.
- Add concise contributor usage/limits, this specification, a verification record
  and the roadmap status. Keep the public material English and product-neutral.
- Do not change `refracto/`, `refracto_browser/`, adapters, example targets,
  Scenario files, ports, assertions, dependencies, locks or package versions.
  Existing Scenario YAML, format 1 and one-level inclusion remain unchanged.
  The CI workflow is allowed to change; the Scenario-format freeze does not freeze
  test infrastructure configuration.
- No private workspace access, product changes, Flow implementation or object-
  absence work. No speculative browser/fixture repair without a reproduction.

## Execution contract

The launcher runs the current Python interpreter's pytest in a dedicated POSIX
process group. Supported hosts for this guarded entry are Linux and macOS;
unsupported hosts fail before launching. Plain pytest remains available with its
existing behavior and is not advertised as externally guarded.

Load the plugin only through this child's explicit `-p` argument. Do not put it
in global conftest/autoload settings or inject it through PYTEST_PLUGINS or
PYTEST_ADDOPTS. Existing nested pytest subprocesses must not overwrite the outer
run's progress. The launcher is a pytest entry, not a general command runner.

Initial defaults, to be checked against real runs:

| Test-infrastructure budget | Default |
| --- | --- |
| Diagnostic request after an unchanged phase | 120 seconds |
| Stop after an unchanged phase | 300 seconds |
| Whole pytest subprocess | 2700 seconds |
| CI job, including installation and diagnostic upload | 60 minutes |

Expose explicit positive finite overrides for local diagnosis and small synthetic
controls. Diagnostic delay must be shorter than the phase stop budget. The suite
ceiling is independent and may be shorter. Reject malformed, zero, negative,
boolean-like or nonfinite configuration before starting a child. These values
are engineering bounds, not product response times or measured performance claims.
Do not increase any product action, polling or state-observation deadline.
Guard options precede `--`; only the tail is passed to pytest. Unknown guard
options fail before launch. CI uses 120-second litmus and 600-second core suite
ceilings within a twenty-minute core job; full tests retain the defaults above.

Use the supervisor's monotonic clock. Progress transitions reset only the phase
deadline, never the suite deadline. Include startup, collection, setup, call,
teardown, session finalization and process exit. A fixture teardown or process
shutdown is part of execution; a passed assertion alone cannot complete the run.
Write progress atomically with an execution identity, owning PID and increasing
sequence. No reusable daemon, server, UI or parallel scheduler is needed.

## Diagnostics and ownership

Create a new output directory for each invocation and reject nonempty output
directories. Retain `progress.json`, `result.json`, `pytest.log` and a stack file.
These are test-launcher diagnostics, not a new RunReport or business status model.
Record budgets, last phase, elapsed times, child exit code, timeout/interruption
reason, diagnostic availability and bounded cleanup outcome.

Use a repository-relative test file, class/function and collected ordinal for
identification. Do not add parameter IDs, values, environment contents, credentials,
command-line dumps or local variables to progress/summary messages. Out-of-root
paths must not expose their parent directories. Print bounded periodic progress
so hosted logs show the active phase without a line for every hook transition.

Register a dedicated faulthandler diagnostic signal in the child, retaining its
file until shutdown. Send it only to the known pytest PID after a readiness
handshake, never to the whole group. Do not compete with pytest's delayed stack
timer. Diagnostic availability is best effort: if startup or native execution
prevents capture, record that fact and still enforce the external deadline.

Write child stdout/stderr to regular files, not supervisor-owned pipes whose EOF
depends on descendants. The supervisor must never wait indefinitely for logs,
communicate(), termination or cleanup. All graceful TERM and final KILL waits are
bounded, including after interrupts, early exits and normal pytest completion.
Default termination grace is 0.1 seconds for requested stack capture, then two
seconds for TERM and two for KILL. Each process inspection is bounded to one
second and may overrun an enclosing grace by at most that bound. Controls allow
a ten-second cleanup margin beyond the execution deadline under normal OS
scheduling. This does not promise hard real-time process or filesystem behavior.
Cleanup addresses only the owned process group; never use broad process-name
kills or touch other browsers. Detect/report surviving live group members after normal
pytest exit; clean them and fail that invocation rather than hide a resource leak.
Zombie-only entries cannot execute or retain output descriptors and do not count
as active group members. Group inspection itself must have a bounded wait.
Permission races must not abandon bounded escalation or erase earlier cleanup
actions. Retain safe operation/exception-type/error-number diagnostics, not
exception messages; permission denial alone never proves successful cleanup.

Descendants that create another session can escape group cleanup. This is not a
process sandbox or a guarantee of complete descendant reclamation. They must not
keep the launcher waiting for pipe EOF. Document this limit and the disposable CI
worker boundary; do not claim the old stall or all resource leaks are fixed.
Hard OS termination, a dead host or uninterruptible kernel work can prevent final
diagnostics; the outer CI job limit remains a separate last resort.

Preserve pytest's ordinary nonzero exit codes and zero only after valid final
progress, child completion and clean owned-group shutdown. Timeout, malformed
guard state, supervisor failure, interruption and incomplete cleanup must exit
nonzero even if the child later exits zero. There is no automatic rerun-to-green.

Raw pytest output and stack files are diagnostic material, not a general secret
redaction facility. Stack files may contain file/function names but no locals.
CI retains artifacts from this public synthetic suite only; the local launcher
does not upload anything. Artifact retention is bounded and failure must not
prevent attempted upload. No private data source is introduced.

## Mechanical acceptance

Use real temporary pytest suites and an independent outer process deadline;
clean up controls in finally blocks so defects in the guard cannot hang its tests.

1. Passing tests, ordinary assertion failure, collection failure, no-tests and
   usage errors preserve exit semantics. No test selection is added to full CI.
2. Reproduce stalls separately in import/collection, setup, call, teardown and
   finalization/process exit. Report the correct available identity and phase,
   collect stacks when ready, and finish unsuccessfully within the configured
   bound plus documented grace. Include a subprocess/native-style blocking wait.
3. A missing readiness handshake and malformed or stale progress cannot become
   a successful guarded run. Nested pytest cannot corrupt the parent record.
4. Exercise a TERM-resistant child, normal parent exit leaving a group child,
   inherited output handles, and supervisor interruption. Check only owned PIDs;
   prove an unrelated process is not killed. State any escaped-session limit.
5. Test strict finite budgets, nonempty output directory rejection and repeated
   invocations. Parameter-value and environment sentinels must not appear in
   guard-generated progress/result output; raw pytest logs are not claimed redacted.
6. CI uses the guard for litmus, both supported core Python versions and the
   complete optional-browser suite, with unique output paths, job ceilings and
   always-attempted diagnostic retention. The coverage sentinel must reject a
   filtered full-suite command or missing browser installation.
7. Run targeted controls, documentation/litmus, core-only suites, and the complete
   real-Chromium suite through the new launcher. Check lock, hygiene and diffs.
   Mechanically compare protected production/declaration/example/dependency files
   against baseline. Audit the public diff and information sources before staging.

Independent audit must challenge both success propagation and bounded failure.
Record actual commands, budgets, observed outcomes, cleanup limits, findings and
corrections. After acceptance use the authorized task branch, PR, green checks,
merge, green main CI and branch cleanup. A retry is recorded as a retry, not a
root-cause repair. Return to a text-only Flow design assessment after delivery;
new Flow expressions still require maintainer review before implementation.
