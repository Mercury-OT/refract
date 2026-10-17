# Mixed anonymous users and included-user mappings: acceptance

Date: 2026-10-17. Result: **PASS for the bounded task**.
Specification: [mixed participants and explicit mappings](anonymous-users-inclusion.md).
Starting and local acceptance HEAD: `68af23a1e88d9742afeb2bb5331681b4cd21f02d`.
The maintainer approved the expression and authorized implementation, independent
audit, architect acceptance, and subsequent public submission after those gates.
This record establishes local acceptance, not hosted CI or publication. The
subsequent task branch, PR, merged commit and CI runs establish delivery.

## Accepted result and limits

Reserved `anonymous` can coexist with named participants. Empty-user declarations
retain implicit anonymous execution, a sole participant remains the default, and
ordinary steps in mixed declarations explicitly select a user. Anonymous actions
never request an account session. Switching back to a named user retains that
user's session. Runtime anonymous attribution remains `None` with generation 0;
declaration and review views show the explicit `anonymous` choice.

`with_users` completely maps child-local participants to distinct parent
participants. Each child leaf is expanded separately into the existing flat
runtime. Multi-user children are permitted only at the existing one-level
boundary. Child pins, expectations, session policies, named results, query
references and failure policies retain their meanings. Unknown, missing,
duplicate or dynamic mappings, anonymous upgrades, anonymous renewal, and
caller overrides are rejected. No new execution loop was introduced.

The two public Documents parents pin identical child bytes. Actual target
decisions exercise creation, owner reads, named-peer refusal and anonymous
refusal. The shared child deliberately accepts 401 or 403; each parent then
checks its precise status and response reason. A separate fixed-403 child mapped
to anonymous correctly fails on an actual 401. A deliberately credential-leaking
driver also fails the unchanged refusal assertions. An anonymous label alone is
not evidence of what an untrusted target or driver actually did.

Real Chromium live and mock runs verify separate cookies, storage, contexts,
credential headers, context reuse, global mock order and cleanup. Wrong user,
generation, context, replayed evidence and inherited credentials cannot pass.
The separate Demo HTTP transport copies only the current session's headers and
keeps core trace attribution authoritative. Its default target still has no real
login or authorization policy; the HTTP peer proves transport isolation only.

Contract continues to check backend recordings without a second request or
authentication. It is not independent account evidence. Sensitive values remain
hidden from default representations, not from arbitrary serialization. No deeper
nesting, multiple anonymous personas, automatic login recovery, new rejection
classification, real-product adoption or measured review-cost saving is claimed.

## Verification and independent finding

Commands ran from the public repository root. Final checks exited 0.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 1978 passed, one existing Starlette/httpx warning, no skips; 235.79 s |
| Fresh dev-only environment, `python -B -m pytest -o addopts='' -q --tb=short` | 1737 passed, one optional Demo collection skip; 36.04 s |
| Isolated `tests/test_opensource_litmus.py` | 3 passed |
| Document, include, onboarding, hygiene and litmus tests | 28 passed |
| Independent core/Documents/include/named-result/query/CLI/impact regression | 558 passed; 2.62 s |
| Independent new UI/browser/Demo transport regression | 59 passed; real Chromium, no skips; 35.88 s |
| Independently authored probes | 558 cardinality/type/wait/mapping cases, 18 cross-include session/result/query checks and 39 malformed-parent impact checks passed |
| Additional real-browser audit probes | Renewal preserved the anonymous context; anonymous requests lacked account credentials; cleanup, mock order and replay rejection passed |
| Maintained Scenario loading | All 28 files loaded |
| Actual `refracto validate examples/documents/scenarios/mapped_anonymous_access.yaml --expand` | Complete mapping, explicit anonymous selection and per-leaf sources shown |
| Child sidecar pins | Both match the same unchanged child bytes |
| `uv lock --check`, repository hygiene, diff and cached-diff checks | Passed; dependencies unchanged; index empty at acceptance |

The isolated Python 3.12 environment was created using `uv sync --locked
--extra dev` with a fresh temporary `UV_PROJECT_ENVIRONMENT`. Playwright, httpx,
FastAPI and uvicorn were independently confirmed absent. Its optional collection
skip does not replace full-suite browser execution. The task adds 194 tests.

Independent audit found one P2 issue: malformed current-parent `users` could
crash change-impact inspection with `KeyError(0)`. The corrected inspection
validates that shape before deriving a mapping, keeps the caller invalid, and
reports no invented effective bindings. Twenty-two full-inspection regressions
cover both shorthand and explicit mappings. The auditor independently retested
the fix; the final full and isolated results above include it. No finding remains.

An exploratory developer command interleaving individual root/browser/Demo test
paths could not find a pre-existing Demo fixture. The collection-only setup plan
reproduced this argument-order issue. Grouped paths passed 108 tests, and both
complete full-suite runs passed; no assertion or product behavior was changed
to hide it. The earlier full run passed 1956 tests before the audit regression
cases were added; it is not substituted for the final result above.

## Accepted public scope

```text
README.md
SCENARIO.md
adapters/demo/api.py
adapters/demo/auth.py
docs/browser-support.md
docs/impact-review.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/anonymous-users-inclusion.md
docs/tasks/anonymous-users-inclusion-acceptance.md
examples/documents/scenarios/mapped_anonymous_access.includes.json
examples/documents/scenarios/mapped_anonymous_access.yaml
examples/documents/scenarios/mapped_peer_access.includes.json
examples/documents/scenarios/mapped_peer_access.yaml
examples/documents/scenarios/shared/access_document.yaml
refracto/declaration/expansion.py
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/projection/sessions.py
tests/browser/test_anonymous_users.py
tests/demo/test_demo_anonymous_users.py
tests/test_anonymous_documents.py
tests/test_anonymous_ui_users.py
tests/test_anonymous_users_inclusion.py
tests/test_users_sessions_core.py
```

Independent audit and architect review found no remaining blocker. Source review
covered tracked and new files: all inputs are the approved neutral expression,
existing public code and synthetic Documents/Demo/browser examples. No private
workspace was accessed or changed. Documents and Demo application policy,
browser support implementation, MANIFESTO, BRAND, CI and dependency files are
unchanged. At local acceptance all 27 files were unstaged, main still matched
origin/main at the starting HEAD, and no submission action had occurred.
