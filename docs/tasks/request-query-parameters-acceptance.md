# Explicit request query parameters: local acceptance

Date: 2026-10-17. Result: **PASS for the bounded task**.
Specification: [explicit request query parameters](request-query-parameters.md).
Starting and acceptance HEAD: `eaca8cb887ad176aa5c9fda4afbf028ed22a2fcd`.
The maintainer approved the complete example and authorized implementation,
independent audit, and acceptance. Submission is not authorized. This record
does not claim publication, hosted CI, or real-product adoption.

## Accepted result

Optional query mappings now work in API actions and UI request constraints.
Format 1 and the approved overall YAML structure remain. Query values reuse
parameters, prior responses, and included named results; preparation, inclusion,
expanded review, change-impact inspection and polling preserve those references.
The new mapping does not introduce expressions, loops, or automatic pagination.

The approved Documents example visibly creates two matching documents and one
other-category document, then reads two separately declared pages using the
observed first-page cursor. Both backend plus contract and explicit-API e2e
execute the unchanged example against a fresh synthetic target. The real target
receives the declared queries and returns the expected distinct documents.
Documents no longer derives query defaults from global Scenario parameters.
Two maintained search declarations were migrated without weakening assertions.

Real Chromium tests independently observe fetch/XHR URLs in live and mock modes.
Declared query equality is exact decoded-string equality; omission leaves query
outside the UI check, while an explicit empty mapping requires no parameters.
Wrong, missing and extra values reach ordinary failed request checks. Multiple
same-path requests require one unambiguous declared-query match. Background or
replayed traffic cannot substitute for the action's evidence. Static resource
queries retain their previous scope rather than inheriting API restrictions.

Unsupported duplicate or malformed encoded API queries fail before forwarding.
Empty strings, zero, false, Unicode and encoded delimiters are preserved.
Resolver, driver, Recorder and normalizer query rewrites cannot turn a mismatch
into a pass. Mock fixture queries are explicit and independent of assertions.
Default query-bearing runtime representations hide query values; this is not
general-purpose redaction or permission to serialize entire reports.

The separate Demo driver sends queries to a real local HTTP peer. Contract
continues to inspect the same backend recordings without sending requests; it
is response compatibility, not an independent query observer. Browser tests
are separate evidence from the explicit-API e2e example. Neither establishes
arbitrary product sorting, database state, review-cost savings, or protection
against a malicious driver that fabricates every observation consistently.

## Verification

Commands ran from the public repository root and exited 0 unless noted.

| Check | Actual result |
| --- | --- |
| Independent `uv run --extra dev --extra demo pytest -q tests/test_query_parameters.py tests/test_query_documents.py tests/demo/test_demo_query.py tests/browser/test_query_parameters.py` | 179 passed: 82 core, 34 Documents, 4 Demo transport, 59 real Chromium; no skips |
| Additional independent probes | 33 passed: 20 in-memory core/reference checks and 13 real Chromium checks |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 1784 passed, one existing Starlette/httpx warning, no skips; 199.08 s |
| `"$TASK_QUERY_CORE_ENV/bin/python" -B -m pytest -o addopts='' -q --tb=short` | 1574 passed, one optional Demo collection skip; 36.51 s |
| Maintained Scenario loading | All 25 files loaded |
| `uv run --locked --no-sync refracto validate examples/documents/scenarios/filter_and_next_page.yaml` | Five steps, five requests, 19 response assertions |
| Expanded example and documented query fragment | Query references visible; documented fragment loaded and resolved actual cursor |
| `uv lock --check` | Passed; dependencies and lock unchanged |
| `bash scripts/check_repository_hygiene.sh` | Passed; supplementary new-file path/language scan passed |
| `git diff --check` and `git diff --cached --check` | Passed; index empty |

The isolated environment is a fresh Python 3.12 environment synchronized from
the existing lock with only the dev extra. Playwright, httpx, FastAPI and uvicorn
were confirmed absent. Its optional skip does not replace full-suite browser
execution. Intermediate development regressions also passed; the final full and
isolated runs above are the acceptance gates.

Additional independent checks covered malformed UTF-8, encoded duplicate keys,
single decoding, mutation of resolver input copies, separately rewritten driver
or normalizer evidence, absent optional raw normalization evidence, strict status
types, and false/empty/zero named results through UI inclusion and review. Real
browser checks covered empty-query selection/ambiguity, bare blank parameters,
encoding rejection before target receipt, and static-resource scope.
One exploratory audit harness initially assumed the document was the last HTTP
request, overlooking subsequent script loading. It was corrected to locate the
document request; all 13 browser probes then passed. No implementation defect,
weakened assertion, skipped browser case, or product change was used to resolve it.

## Accepted public file scope

```text
SCENARIO.md
adapters/demo/api.py
adapters/demo/resolver.py
adapters/documents/api.py
adapters/documents/resolver.py
docs/browser-support.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/request-query-parameters.md
docs/tasks/request-query-parameters-acceptance.md
examples/documents/scenarios/continue_after_failure.yaml
examples/documents/scenarios/create_list_delete.yaml
examples/documents/scenarios/filter_and_next_page.yaml
refracto/declaration/binding.py
refracto/declaration/expansion.py
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/normalization.py
refracto/ports.py
refracto/projection/backend.py
refracto/projection/frontend.py
refracto/projection/ui_stepwise.py
refracto/query.py
refracto_browser/_support.py
tests/browser/app.html
tests/browser/test_query_parameters.py
tests/demo/test_demo_query.py
tests/test_documents_failure_continuation.py
tests/test_query_documents.py
tests/test_query_parameters.py
tests/test_second_adapter.py
```

Independent implementation audit and architect review found no remaining blocker.
Public source review includes new files, not just tracked diffs: all examples,
targets, probes and explanations are synthetic or derived from the existing
public repository and the approved neutral example. No private workspace was
read or modified. Public Documents and Demo application sources, MANIFESTO,
BRAND, CI, and dependency files are unchanged. The browser test laboratory gained
fixed query-producing controls solely for synthetic tests. No staging, branch
creation, commit, push or PR occurred. Public main
still equals the unchanged origin/main at the recorded starting HEAD.
