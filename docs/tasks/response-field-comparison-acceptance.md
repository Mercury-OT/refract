# Complete response-field comparison: acceptance

Date: 2026-10-18. Result: **PASS for the bounded task**.
Specification: [complete response-field equality and inequality](response-field-comparison.md).
Starting HEAD: `73b356f326f828d087dbc8a7e38849123da33cfe`.
The maintainer approved the expression and authorized specification, development,
independent audit, architect acceptance, and public submission after those gates.
This record covers local acceptance. The subsequent task PR, merged commit and
hosted CI separately establish delivery.

## Accepted behavior and limits

Format 1 and the existing structure remain. Response `field_equals` compares a
complete finite JSON-like value, including nested objects/lists; the new
`field_not_equals` checks its complement only when both values are usable.
Object key order is immaterial, but all keys must match. Lists retain order and
length. Types are strict, including boolean/integer and integer/float distinctions.
Missing current fields fail both checks. Malformed observed values produce ERROR;
missing, null or invalid response dependencies block the consumer before action.
Other assertion and transport value domains remain bounded as before.

Existing parameter, response and included-result references remain the only
value mechanisms. Runtime response dictionaries are not reparsed as references.
One-level inclusion, user/session attribution, continuation/stop and polling rules
are preserved. Stable owned snapshots protect prior normalized containers and
current expectations from later mutable-buffer reuse. This is not a defense
against an adapter deliberately inventing observations. Unrelated opaque fields
do not acquire a comparison-domain restriction.

Contract retains every equality/inequality constraint, including both on the same
field, and resolves nested references against actual provider evidence. It sends
no additional request and is not an independent evidence source. Container and
inequality diagnostics do not print nested keys or contents. Relevant contract
value fields are hidden from default representations. Existing scalar equality
diagnostics remain; arbitrary serialization and callback exceptions are not
claimed universally safe.

The exact approved four-step Records declaration and a separate enveloped
Documents consumer run against independent stateful synthetic targets. A fault
that actually modifies stored content while returning 403 is detected by the
final read. Controls also cover missing content, wrong objects, equal error
responses, incorrect refusal reasons, invalid sessions, list order and legitimate
changes. These prove the selected normalized field's behavior, not all database
state, independent authorization-decision evidence or production adoption.

## Verification

Commands ran from the public repository root. All final checks exited 0.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 2727 passed; real Chromium, no skips, one existing Starlette/httpx warning; 321.52 s |
| Fresh dev-only Python 3.12: `python -B -m pytest -o addopts='' -q --tb=short` | 2354 passed, one optional Demo collection skip; 35.45 s |
| `tests/test_response_field_comparison.py`, `tests/test_field_comparison_consumers.py`, `tests/test_field_comparison_documentation.py`, `tests/test_declaration.py`, `tests/test_scenario_include.py` | 509 passed; independent rerun 1.60 s, architect rerun 1.39 s |
| New real Chromium comparison file | 38 passed with live/mock traffic, no skips; 29.42 s before the compatibility correction, also covered by final full regression |
| New independent consumer file | 71 passed; 251 passed with existing Documents regression |
| Product-agnostic core litmus | 3 passed |
| Maintained Scenario loading | All 32 declarations loaded |
| Actual CLI validation | Both new examples valid; four requests and 15 response checks each; expanded Records review inspected |
| Lock, repository hygiene, diff and cached-diff checks | Passed; dependencies and CI unchanged; index empty during acceptance |

The isolated environment was freshly installed with `uv sync --locked --extra dev`
and Python 3.12; Playwright, httpx, FastAPI and uvicorn were confirmed absent.
Its optional collection skip does not replace real-browser verification. The task
adds 319 tests over the starting full-suite count.

## Independent audit and corrections

Independent final audit: **PASS**, with no unresolved findings. The reviewer
inspected the implementation, examples, specification, browser tests and public
documentation without changing controlled files. In addition to the 509-test
rerun, independent probes generated 4000 strict typed nested-value pairs and
performed 24000 comparator, contract and missing-field checks. Six malformed
nested-source probes confirmed pre-action blocking in backend and e2e.

One P2 compatibility issue was found and closed. Blanket deepcopy of every
normalized field caused existing success/presence-only checks with an unrelated
lock or immutable mapping to fail. The reviewer reproduced the regression and
confirmed the starting implementation passed those probes. Snapshots now copy
only exact built-in dictionaries/lists with a memo, preserving cycles for later
validation and leaving opaque leaves untouched. Comparisons reject unsupported
values, dependencies block, and contract binding derivation is inside its error
boundary. Independent lock, immutable-mapping, copy-hook, shared-container and
cycle controls passed after correction.

The first dev-only regression found four old tests that deliberately rejected
container equality. Their bounded-domain controls were moved to still-scalar
header/state/ID positions, and explicit legal container neighbors were added.
This updates the approved semantics rather than weakening unrelated validation.
That initial run was 4 failed, 2337 passed, one skip and is not acceptance evidence.
A pre-correction full run was interrupted after 251 passing tests because the
audited implementation had changed; the complete final run above supersedes it.
A redundant developer broad run was also interrupted, not reported as a pass.

Architect acceptance: **PASS**, based on the independently closed findings,
complete final full and isolated regressions, exact approved example, bounded
evidence claims and scoped public information review. Hosted CI remains mandatory
before merge, followed by main CI and branch cleanup.

## Public information and accepted scope

Sources are the approved neutral expression and existing public code. Examples
use synthetic records/documents and loopback services, with no private product
names, paths, source data, evidence or measurements. New files were separately
inspected because tracked-file hygiene does not inspect untracked additions.
The private workspace was not accessed or changed. MANIFESTO, BRAND, dependencies,
CI and existing browser-support implementation remain unchanged.

Accepted public file scope (26 files):

```text
SCENARIO.md
adapters/documents/normalizer.py
adapters/documents/resolver.py
docs/onboarding.md
docs/roadmap.md
docs/tasks/response-field-comparison.md
docs/tasks/response-field-comparison-acceptance.md
examples/documents/app.py
examples/documents/scenarios/rejected_update_preserves_content.yaml
examples/minimal/rejected_update_preserves_content.yaml
refracto/contract/store.py
refracto/declaration/binding.py
refracto/declaration/field_comparison.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/vocabulary.py
refracto/normalization.py
refracto/projection/backend.py
refracto/projection/contract.py
refracto/projection/ui_stepwise.py
tests/browser/test_response_field_comparison.py
tests/test_declaration.py
tests/test_field_comparison_consumers.py
tests/test_field_comparison_documentation.py
tests/test_response_field_comparison.py
tests/test_scenario_include.py
```
