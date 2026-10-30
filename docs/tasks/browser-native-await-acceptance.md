# Native-await association: acceptance record

Date: 2026-10-30. Starting main: `a14965a`.
Scope: [approved specification](browser-native-await.md).
Status: independent mechanism and consumer audits and final local architect
acceptance passed. Full-suite validation passed 4789 tests with one existing
third-party warning in 630.86 seconds. The maintainer authorized submission after
these gates; the associated task PR is the authority for merge and hosted checks.

## Maintainer summary

- The unchanged synthetic async frontend can now supply request evidence after
  native await: its nine previous association failures pass.
- The same ten Scenarios pass against both implementations; no adapter, target,
  core, YAML, vocabulary, dependency or CI changes were needed.
- Background, synthetic-event and old-action work cannot impersonate the current
  action. Missing or unsupported ancestry still prevents a required check passing.
- Audit found and closed two real issues: unconsumed response completion and
  debugger-induced pauses across navigation.
- This is bounded Chromium invocation association, not universal async support,
  completion proof, independent server tracing or measured human cost savings.

## Mechanism and audit

Separate real-browser feasibility probes established the nearest invocation
marker through supported await/Promise.then ancestry. An arbitrary ancestor,
matching endpoint, source function, response or time window was not sufficient.
Timer edges and null scopes were explicitly rejected. An Error.stack/async-wrapper
alternative was rejected because it was more fragile and could change synchronous
return semantics. Invocation ownership does not imply awaited completion.

The implementer added 54 focused parser/Chromium cases. An independent reviewer
reran all 54 (including the 22 parser cases) and 11 selected existing
single-origin/live/mock regressions. Additional actual-collector controls confirmed:

| Control | Observed outcome |
| --- | --- |
| Synthetic nested events, timers, queueMicrotask and animation callbacks | No current-action traffic; observed background data remains diagnostic. |
| Shared promises, repeated callbacks, old producer returned by a later action | Original invocation retained; no reassignment to the current action. |
| Missing/duplicate fetch completion claims | Rejected before delivery: zero HTTP requests and zero accepted traffic. |
| Foreground and timer send the same request | Two actual requests, one response clone; background is not passively drained. |
| Unconsumed response, including a 1 MiB body | Complete evidence; original response remains unconsumed and readable. |
| Oversize body, abort and CORS denial | Visible collection failure. |
| Parser-level and handler debugger statements, click navigation and reopening | Zero pause events; subsequent owned requests remain associated. |

The initial implementation timed out on an unconsumed 69-byte post-await
response. The fix registers an early response callback and claims its exact local
handle only after native ownership classification, before delivery. A separate
finding showed that skip-pauses alone did not survive navigation. Disabling
breakpoints retained async ancestry without adding stepping or product pauses.
Both fixes were independently reproduced, not accepted solely from source review.

## Frozen consumer results

All 85 frozen inputs, including 74 YAML files, were byte-identical. The consumer's
17 Python/JavaScript/YAML source hashes match the baseline. The two final audited
panels also match every current engine source hash. No case was dropped.

| Panel | Units | PASSED | FAILED | Elapsed seconds |
| --- | ---: | ---: | ---: | ---: |
| Actual starting-main baseline | 20 | 11 | 9 | 25.70 |
| Independently rerun candidate | 20 | 20 | 0 | 25.97 |
| Independently rerun maintenance configuration | 20 | 20 | 0 | 25.70 |
| Candidate repeat 1 | 20 | 20 | 0 | 25.73 |
| Candidate repeat 2 | 20 | 20 | 0 | 25.59 |

Each final audited panel contains 30 real non-preflight API requests, 30 associated
recordings and 16 browser-native preflights. Actual origin, credential destinations
and absence of injected trace/private marker headers were checked. The maintenance
variant changes only the established selector/API-prefix bindings. Adapter code
remains 61 token-bearing Python lines; human effort is unmeasured.
The reusable browser package is 1290 token-bearing Python lines, versus 1206
in the prior accepted panel. Target application, harness and YAML counts remain
151 Python lines, 167 Python lines and 532 nonblank YAML lines respectively.
The repeat runs describe these fixed executions only, not a reliability rate or
a stable performance benchmark. All 100 executions, including baseline failures,
remain in the recomputed panel report.

Three independent actual-HTTP counterexamples still fail: wrong created code,
stale read content, and unavailable async ancestry. The last has no associated
recording and retains the existing missing-request error. This is not evidence
for other products or asynchronous patterns outside the tested bounds.

One intermediate maintenance measurement detected changing engine bytes and
aborted. It was not accepted as final evidence. Both final panels were rerun after
the production freeze and passed source-inventory checks.

## Commands and checks

The commands below reproduce the checks from the public repository; panel labels
are descriptive. Baseline measurement ran before implementation on `a14965a`;
reproducing it later requires that source revision, not re-labelling a
current-engine result as a baseline.

```sh
uv run --frozen pytest -o addopts='' -q tests/test_native_await_association.py tests/browser/test_native_await.py
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label await-baseline --output /tmp/browser-await-baseline.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label candidate --output /tmp/browser-await-audit-accepted-candidate.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label maintenance --maintenance --output /tmp/browser-await-audit-accepted-maintenance.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label await-repeat-1 --output /tmp/browser-await-repeat-1.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label await-repeat-2 --output /tmp/browser-await-repeat-2.json
uv run --frozen python -m examples.browser_multi_origin.measure --baseline /tmp/browser-await-baseline.json --candidate /tmp/browser-await-audit-accepted-candidate.json --maintenance /tmp/browser-await-audit-accepted-maintenance.json --repeat /tmp/browser-await-repeat-1.json --repeat /tmp/browser-await-repeat-2.json --output /tmp/browser-await-cost.json
uv run --frozen pytest -o addopts='' -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
```

Fresh dev-only Python 3.11 and 3.12 environments each passed 4081 tests with one
optional-dependency skip. The litmus, Scenario/include documentation and existing
stabilization/boundary sentinels passed 101 tests. Focused tests and final audited
consumer commands exited zero. The complete suite passed 4789 tests with one
existing third-party warning; lock, hygiene and diff checks passed. The accepted
scope is thirteen public files. No unresolved audit finding remains.

Public source review uses only this repository's neutral examples, browser
observations and independent synthetic controls. No private repository was read
or modified. No claim is made about private integrations, human review quality,
whole-browser memory bounds or adversarial in-process collectors.
