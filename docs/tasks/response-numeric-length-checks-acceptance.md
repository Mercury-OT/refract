# Response numeric and list length checks: acceptance

Date: 2026-10-18. Result: **PASS for the bounded task**.
Specification: [response numeric and list length checks](response-numeric-length-checks.md).
Starting HEAD: `75db346531f68aeb95aa7ce549750de7925ac10e`.
The maintainer approved the expression, examples and failure rules, authorized
implementation and audit, and separately authorized submission after acceptance.
This record establishes local acceptance, not the later PR, merge or hosted CI.
No private workspace was accessed or changed.

## Accepted behavior

`field_compare` checks a finite numeric response field against a literal or
existing reference. `collection_length` checks the actual length of a finite
JSON-like list against a nonnegative integer. Both accept the existing five
comparison operators. Numeric ordering does not coerce large integers to floats;
equality remains type-strict. Booleans and numeric strings are not numbers.
An actual empty list is distinct from a missing field.

Missing or valid wrong-type current values fail the check. Malformed examined
data produces ERROR. Invalid fixed thresholds are rejected at loading; unusable
response-derived thresholds block the consuming action before authentication,
without partial bindings. Independent continuation and explicit stop retain
their existing behavior. New diagnostics omit operand values and list contents;
this does not establish safe arbitrary serialization or change older diagnostics.

The evaluator is shared by backend, API/live UI e2e, frontend mock responses,
polling and contract. Contract retains every bound and uses actual provider
thresholds, not declaration expectations or diagnostic bindings. It does not
send requests or become an independent observer. Format 1, existing reference
shapes, one-level inclusion, named results, users and sessions remain unchanged.

The approved five-step Documents example and an independent Records example
create two matching records and one unrelated record, check the first page,
then follow its actual cursor to the second page. Content checks remain alongside
size checks. The Documents adapter derives its count from observed list data;
that count is not independent evidence. The Records consumer separately exposes
faulty reported counts and faulty lists. No production adapter or target changed.

## Final verification

Commands ran from the public repository root; final gates exited 0.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 3419 passed, real Chromium, no skips, one existing Starlette/httpx warning; 426.37 s |
| Fresh dev-only Python 3.12: `python -m pytest -o addopts='' -q --tb=short` | 2943 passed, one optional Demo collection skip; 40.06 s |
| Independent audit: five new test files | 390 passed, including all 45 real Chromium live/mock cases, no skips; 38.28 s |
| Core and inclusion compatibility regression | 1029 passed; 1.57 s |
| Consumer/documentation and existing Documents query regression | 84 passed |
| Core litmus and new documentation checks | 7 passed; 0.21 s |
| Maintained executable YAML | All 50 loaded; historical authoring inputs are not executable Scenarios |
| Actual CLI validation and expanded review | Both new examples retain five requests, 25 response checks and all eight numeric/length constraints |
| Lock, repository hygiene, diff and cached-diff checks | Passed; dependencies and CI unchanged; index empty during local acceptance |

The fresh isolated environment was installed with `uv sync --locked --extra dev`
and Python 3.12. Playwright, httpx, Starlette and uvicorn were confirmed absent.
The optional collection skip does not replace real browser verification. The full
suite adds 390 passing tests over the starting revision.

## Independent audit and architect acceptance

Independent audit: **PASS**, with no unresolved findings. The reviewer read the
specification, all implementation changes, examples and tests without editing
files. An additional 630 read-only probes covered rational-oracle comparison,
huge integers, wrong types, malformed data and actual-provider threshold replay.
Falsifying diagnostic bindings did not change contract's source of evidence;
changing the retained provider threshold changed the outcome appropriately.

Architect verification added 4000 deterministic integer/float comparisons against
an independent rational-number oracle, all passing. Full regression, isolated
regression, documentation loading, actual CLI expansion and source review passed.
Fault controls cover false counts, empty/oversized lists, ignored filters,
repeated pages, unavailable cursors and malformed values. They establish bounded
capability, not real-product adoption, complete pagination or maintenance savings.

Architect acceptance: **PASS**. Required PR CI, post-merge main CI and branch
cleanup remain submission gates. No new expression or scope change is required.

## Public source review and accepted files

Sources are the approved neutral expression and existing public code. Examples
use synthetic documents/records and loopback services. New untracked files were
reviewed separately because tracked-file hygiene does not cover them. No private
names, paths, data, evidence or measurements are included. MANIFESTO, BRAND,
dependencies, CI, ports, adapters and execution loops are unchanged.

Accepted scope (19 files):

```text
SCENARIO.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/response-numeric-length-checks.md
docs/tasks/response-numeric-length-checks-acceptance.md
examples/documents/scenarios/check_page_limits.yaml
examples/minimal/check_page_limits.yaml
refracto/contract/store.py
refracto/declaration/binding.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/numeric_comparison.py
refracto/declaration/vocabulary.py
refracto/projection/backend.py
tests/browser/test_response_numeric_length.py
tests/test_numeric_check_consumers.py
tests/test_numeric_check_documentation.py
tests/test_numeric_length_inclusion.py
tests/test_response_numeric_length.py
```
