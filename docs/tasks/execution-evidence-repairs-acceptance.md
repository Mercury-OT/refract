# Execution-evidence repair verification

Specification and approval: [bounded repairs](execution-evidence-repairs.md),
2026-11-08. Starting main: `b3a828bb7cb1218dbc4956dfd770ce9dded8c06a`.
Status: PASS. Independent core and browser audits and architect acceptance passed;
final frozen-code regression completed on 2026-11-09. The maintainer authorized
task-branch submission after these gates. Hosted CI, merge and cleanup are
recorded separately by the associated PR and commit history.

## Result and retained limits

DomainResult, RunReport and FlowReport now require exactly PASSED for passed.
DEGRADED is not a successful strict gate. Aggregate statuses, continuation and
Flow publication rules have not changed. A step ERROR can still aggregate to
FAILED; the step detail distinguishes unavailable execution evidence from an
observed product mismatch. The Python migration is in CHANGELOG.md.

Backend and live UI validate exact StateFacts and current trace identity before
and after taking an owned copy, including ordinary polling and its final read.
Wrong or missing correlation is ERROR. No probe remains degradation; complete
but nonmatching facts remain FAILED. API request-side trace fallback without a
server echo remains valid; a contradictory response trace is rejected.

Post-hover/Escape mock quarantine remains active, including retained Flow
contexts. Actual helper-blocked API work now produces mock_background_blocked,
not an ordinary page assertion failure or silent success. It consumes no fixture
and cannot fall through to live API services. An independently associated later
action may have consumed its own fixture before a late block arrives; that does
not turn the blocked background request into evidence. Ordinary unrelated native
connection failures remain diagnostic; legacy acquisition errors retain their
existing behavior.

Optional native diagnostic body retrieval reserves work before reentrant RPCs.
Actual reads plus pending reservations are capped at 100 per context; each
collection samples at most eight already queued optional bodies. Existing byte
limits remain. Associated evidence and exact mock order are not discarded.
Collection checks the current action deadline rather than draining a moving
background queue. Truncation is visible and is not a product assertion.

Fixed safe categories survive helper, core and sensitive-header wrappers. No
raw exception message or arbitrary class name is used. A cleanup failure does
not erase the primary action cause. Whole-page uncaught exceptions and unhandled
rejections remain sticky errors, including unrelated timers; console.error alone
is nonfatal. This policy does not establish action ownership and remains a
compatibility limitation, not a new exception-filtering capability.

## Reproduction, corrections and independent review

Before repair, neutral real-browser controls reproduced live success versus
mock failure on reopen after hover/Escape, with an unused background fixture.
A separate missing-ID control returned DEGRADED with passed true. State controls
showed backend accepting malformed/unrelated facts that live UI rejected.
The baseline core oracle produced 40 expected failures and 32 passes against
the old implementation after correcting its polling fixture to a legal GET.

The reported low-CPU failure frequency was not reproduced locally: the two
original pressure tests passed their initial three isolated runs each. A
controlled slow body reader did establish excessive actual retrieval work:
100 retained records could require 133 reads; a slower control performed 131
reads and exceeded the action deadline. A probe test passing while observing
that failure is not a successful product execution.

The first larger browser repair regression failed ten low-volume diagnostic
controls because truncation was too aggressive (185 checks, exit 1, complete
cleanup). Bounded deferral restored those observations without recursive optional
reads. The thirteen selected repaired controls and pressure checks then passed.
Independent audit also found that a native body-read timeout lost its category;
the fixed handler and safe cleanup-secondary path were rechecked independently.
These failed iterations are not substituted for final regression evidence.

Independent core review passed 62 additional probes and 313 focused repository
regressions. It checked strict gates, state identity and ownership, polling,
sensitive headers, primary-plus-cleanup failures and Flow cleanup. No remaining
finding. Independent browser review passed 20 additional offline probes and
23 actual Chromium probes (25.8 seconds, exit 0, complete cleanup). Its controlled
0/30/100 ms optional-body delays preserved one exact foreground response, bounded
reads plus pending work, and no recursively nested optional read. This does not
prove performance on arbitrary hosts or reproduce a particular failure rate.

The separate consumer panel passed 36 real-browser checks across two guarded
runs: 24 mock/Flow/page-policy controls and 12 safe-cause controls. Timeout,
unauthorized destination, duplicate target, malformed rendering and cleanup
failures originated from actual BrowserSupport paths rather than manually
throwing the category exception. Final RunReport reasons and privacy were checked.
Blocked destinations received no HTTP; cleanup completed.

The final focused browser regression passed all 328 checks in 268.07 seconds,
guard exit 0, no diagnostic request and complete cleanup. It includes the ten
previously failing low-volume controls, legacy/native hover and Escape, policy,
slow diagnostic reads, query parameters and form requests on the frozen code.

## Reproducible checks

Run from the public repository with the appropriate optional browser dependencies
and installed Chromium. Every guard output directory must be new.

```sh
python -m pytest tests/test_execution_evidence_repairs.py tests/test_browser_diagnostic_work.py
python -m pytest tests/browser/test_framework_failure_reporting.py tests/browser/test_native_diagnostic_body_budget.py
python scripts/run_tests.py --output-dir /tmp/evidence-repair-full -- -o addopts='' -q
python -m pytest tests/test_opensource_litmus.py tests/test_stabilization_documentation.py tests/test_minimal_onboarding.py
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Dev-only checks use separate Python 3.11 and 3.12 environments installed with
only `.[dev]`, the same guarded entry and a 600-second suite budget. They do not
claim to execute Chromium. Final frozen-code results were 4945 passed and one
optional collection skip in each environment, exit 0 and complete cleanup:
46.46 seconds for Python 3.11 and 47.46 seconds for Python 3.12.

The final full suite passed 6190 tests, zero skips and one existing third-party
Starlette/httpx deprecation warning in 1119.05 seconds. The guard exited 0 in
1119.40 seconds with no diagnostic request and complete cleanup. Production
source hashes were unchanged after the freeze. The staged-file hygiene check
then required trailing slashes on four synthetic documentation-domain URLs in
one offline test file; all 20 tests in that file passed again. No production or
assertion behavior changed. Other subsequent edits record acceptance.
The offline litmus and documentation checks passed; lock, repository hygiene and
diff checks passed. Vocabulary and existing Scenario YAML fences are byte-identical
to the starting main. No dependency or CI change was required.

## Accepted information boundary

Sources are public implementation, the approved repair decisions and neutral
synthetic pages and controls. No private product or workspace is a source or a
changed target. Public text is English. Existing YAML, schema version, include
depth, vocabulary, dependency lock and CI configuration remain unchanged.
No object-absence, browser compatibility or declaration capability is added.
Submission, hosted CI, merge and branch cleanup are separate delivery gates;
local audit success alone does not claim their completion.
