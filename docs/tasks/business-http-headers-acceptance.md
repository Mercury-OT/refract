# Business HTTP headers: acceptance

Date: 2026-10-17. Result: **PASS for the bounded task**.
Specification: [business request headers and response-header checks](business-http-headers.md).
Starting HEAD: `0c148655be28d9d5b178ddf42b90b8a3f7a82636`.
The maintainer approved the expression and authorized specification, development,
independent audit, architect acceptance, and subsequent public submission after
those gates. This record describes local verification, not hosted delivery.
The task PR, merged commit and CI runs separately establish publication.

## Accepted behavior and limits

Format 1 and the overall declaration remain unchanged. Optional business headers
belong to `do.request` or a UI action's `expect.request`. Names are literal HTTP
tokens and case-insensitive; values are exact bounded strings or existing
references resolving to strings. Empty values remain present. Credentials and
transport controls are not business input, and custom session-header collisions
must be rejected before sending. Existing include, user/session, query, reference,
and continuation boundaries remain.

`header_equals` and `header_absent` use raw, duplicate-preserving response pairs
captured before normalization. None means unavailable evidence, never absence.
Multiple occurrences of an asserted name are an error; unrelated repeated headers
are allowed. Valid wrong or missing values fail the corresponding assertion.
Normalizers and Recorders cannot repair or rewrite this evidence.

API reference drivers capture the actual built HTTP request or exact in-process
target invocation. Browser support collects the full browser request block,
including visible credentials, plus the effective trace/private-marker rewrite.
Independent HTTP peers check the business values that actually arrive. Browser
forwarding can add transport-owned headers; the helper does not invent those
values or claim packet-level observation. Mock response evidence is read from
the actual fulfilled browser response, including generated headers, rather than
declaring a bare fixture mapping complete. Expectations do not populate actual
request evidence. Contract checks protected backend responses without sending
another request or becoming an independent observer.

The approved three-step records example and a separate enveloped Documents
consumer exercise retry/read behavior. A deliberately defective service creates
another record but returns the original ID; the unchanged final name count
detects the duplicate. These examples use fresh synthetic targets, immediate
complete list reads and no name uniqueness constraint. They do not prove
production adoption, concurrent retry correctness, persistence, key expiry,
global idempotency semantics, or measured maintenance savings.

New header-bearing fields and the legacy raw-header mapping are hidden from
default representations. Header-aware port boundaries suppress exception text
that could contain those values. This is not arbitrary serialization safety,
universal redaction, or protection from unobserved data retained by arbitrary
custom code. Header-free legacy callbacks without captured header data retain
their prior diagnostics. No response-header references, upload/body grammar,
expressions, unique-value generator, new dependency, or CI change is included.

## Verification

Commands ran from the public repository root. All final checks exited 0.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 2405 passed with real Chromium, no skips, one existing Starlette/httpx warning; 295.64 s |
| Fresh dev-only Python 3.12: `python -B -m pytest -o addopts='' -q --tb=short` | 2073 passed, one optional Demo collection skip; 35.19 s |
| Fresh dev-only `tests/test_opensource_litmus.py` | 3 passed |
| Core header, Documents header and header-documentation tests | 336 passed; 0.77 s |
| Those checks plus Scenario/onboarding/include documentation | 357 passed; 0.56 s |
| Browser developer's header/query/lifecycle/user-binding regression | 152 passed with real Chromium, no skips; 108.05 s |
| Adapter developer's transport/Documents/regression checks | 177 passed, no skips |
| Independent focused core/Documents/docs/real-HTTP checks | 311 passed before final audit controls |
| Independent include/user/continuation/query/header regression | 774 passed |
| Independent final header/report/frontend/e2e/continuation controls | 536 passed; 0.34 s |
| Maintained Scenario loading | All 30 loaded |
| Actual CLI validation and expanded review | Both new examples valid; approved records header references and obligations preserved |
| Lock, repository hygiene, diff and cached-diff checks | Passed; dependency and CI files unchanged; index empty during acceptance |

The dev-only environment was freshly installed with `uv sync --locked --extra dev`
and Python 3.12. Playwright, httpx, FastAPI and uvicorn were independently confirmed
absent. Its collection skip does not replace the full browser run. The first
full regression passed 2383 tests with one existing warning in 296.01 s before
the final audit fixes; it is not substituted for final verification.

## Independent findings and corrections

Two P2 findings were fixed and independently retested:

1. A polling readiness timeout using SKIP retained failed request-header checks,
   but previously aggregated as DEGRADED. Any actually failing check now makes
   the domain and run FAILED. The step retains SKIPPED and the later steps remain
   BLOCKED, preserving timeout control flow. Correct request evidence with only
   a readiness timeout remains DEGRADED. Ordinary failed assertions still continue.
2. Header-free UI declarations can still return sensitive raw headers. Sensitivity
   is now promoted from returned traffic, diagnostic and mock response blocks
   before validation, protecting later action/snapshot/cleanup exceptions even
   after evidence rejection. The original Cookie cleanup-leak probe and a
   malformed request-pairing probe both produce value-free errors.

Independent probes also checked duplicate detection after an earlier mismatch,
raw-pair mutation, invalid-reference atomicity and both polling outcomes. No
independent finding remains. Architect acceptance includes the final full-suite
and isolated results above. The task adds 427 tests over its starting baseline.

Development diagnostics were retained honestly: an exploratory `--ignore` test
command still collected browser tests because of an existing collection hook,
and was interrupted during concurrent browser development. Its failures were
not acceptance evidence. Corrected grouped checks passed. An exploratory audit
command named nonexistent files and ran no tests; corrected invocations passed.
The browser wire-block experiment exposed transport-added headers and led to the
explicit observation-boundary documentation, not fabricated observations.

## Public information and scope

Sources are the approved neutral expression and existing public code. Examples
use synthetic records/documents and loopback services. New files were separately
inspected for source disclosure, local paths, hosts and English-only prose because
the tracked-file hygiene script cannot inspect untracked additions. Non-ASCII
test inputs use equivalent escaped source literals. No private workspace was
accessed or changed. No real product source, names or evidence entered the task.
MANIFESTO, BRAND, dependencies and CI remain unchanged.

Accepted public file scope (39 files):

```text
SCENARIO.md
adapters/demo/api.py
adapters/demo/resolver.py
adapters/demo/ui.py
adapters/documents/api.py
adapters/documents/resolver.py
docs/browser-support.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/business-http-headers.md
docs/tasks/business-http-headers-acceptance.md
examples/documents/app.py
examples/documents/scenarios/idempotent_create.yaml
examples/minimal/idempotent_create.yaml
refracto/contract/store.py
refracto/declaration/binding.py
refracto/declaration/expansion.py
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/declaration/vocabulary.py
refracto/headers.py
refracto/normalization.py
refracto/ports.py
refracto/projection/backend.py
refracto/projection/contract.py
refracto/projection/frontend.py
refracto/projection/ui_stepwise.py
refracto/report.py
refracto_browser/_support.py
tests/browser/adapter.py
tests/browser/app.html
tests/browser/conftest.py
tests/browser/test_business_headers.py
tests/demo/test_demo_headers.py
tests/test_business_headers.py
tests/test_header_documentation.py
tests/test_header_documents.py
```

Submission must use a dedicated branch and PR, successful PR checks, a successful
post-merge main run, then branch cleanup and clean main synchronization. No
submission or hosted success is implied by this local record.
