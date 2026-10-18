# Bounded response member references: acceptance

Date: 2026-10-18. Result: **PASS for the bounded task**.
Specification: [bounded response member references](response-member-references.md).
Starting HEAD: `b7996c47d4e857aacb52933add29bf37cc585f19`.
The maintainer approved both expressions and authorized specification,
development, independent audit, acceptance and subsequent public submission.
This is local acceptance; the task PR, merge and hosted CI separately establish
delivery. No private workspace was accessed or changed.

## Accepted behavior

Format 1 and the existing structure remain. A local response reference may read
one literal dictionary `key`, or use `matching` and `member_field` to read from
exactly one observed list member. Whole-field references are unchanged. Matching
uses strict types and all predicates on the same member. Dots and slashes remain
literal key characters, not paths. No first-item fallback, defaults, recursive
selection, automatic pagination or new named-result interface is introduced.

Sources are actual retained normalized responses. Missing, malformed, ambiguous,
null or unusable selected data blocks the consuming action atomically. Falsy
values are retained wherever the existing use position permits them. Selected
containers are copied without modifying evidence. Selection diagnostics and
internal reference identities do not expose predicate or selected values;
generic serialization and existing scalar diagnostics are not universally redacted.

Backend, API e2e, live UI and frontend mock execution share existing preparation.
Contract checks actual provider selection and use-site legality without sending
requests or claiming independent evidence. One-level includes preserve selectors,
parameter substitutions, named-result boundaries, expansion and impact review.

The approved Records create/list/update/read flow and a separate dictionary flow
run against independent synthetic Records and Documents consumers. The Documents
normalizer retains the complete observed dictionary alongside existing aliases;
it does not select using expectations or change product behavior. Real Chromium
controls cover live and mock traffic. These are capability checks, not evidence
of private-product adoption, global uniqueness or reliable UI object identity.

## Final verification

Commands ran from the public repository root; final gates exited 0.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 3029 passed, real Chromium, no skips, one existing Starlette/httpx warning; 377.67 s |
| Fresh dev-only Python 3.12: `python -B -m pytest -o addopts='' -q --tb=short` | 2598 passed, one optional Demo collection skip; 36.94 s |
| New real Chromium member-reference tests | 58 passed, no skips; 47.19 s; also covered by the final full suite |
| New consumers/documentation plus existing Documents/query/comparison tests | 189 passed; 1.31 s |
| Corrected core and include regression | 657 passed; 1.53 s |
| Independent audit regression | 823 passed; 1.72 s |
| Core litmus and member-reference documentation tests | 9 passed; 0.25 s |
| Maintained executable YAML | All 48 loaded, including four new declarations; historical authoring inputs are not executable Scenarios |
| Actual CLI validation and expanded review | Records list flow: four requests, 15 response checks; dictionary flow: two requests, eight response checks; selectors preserved in expanded review |
| Lock, repository hygiene, diff and cached-diff checks | Passed; dependencies and CI unchanged; index empty during local acceptance |

The isolated environment was freshly installed with `uv sync --locked --extra dev`
and Python 3.12. Playwright, httpx, FastAPI and uvicorn were confirmed absent.
Its optional collection skip does not replace browser verification. The full
suite adds 302 passing tests over the starting revision.

## Independent audit and corrections

Independent audit: **PASS**, with no unresolved findings. The reviewer inspected
the specification, code, examples, documentation and browser tests without changing
files. A separate 1500-case randomized two-predicate oracle agreed with strict
selection semantics. Public-information review covered all new untracked files,
not only files visible to tracked-file hygiene.

One P1 was found and closed: contract initially validated selection but not its
use site. A corrupted selected ID could be invalid for a path while a retained
downstream recording still allowed contract to pass. Selector-bearing contract
consumers now reuse `prepare_step()` without executing actions. Forty-eight
regression cases cover both selector forms, path/query/header/assertion legality
and selected include parameters. The reviewer's ten independent invalid-path
probes now produce ERROR. Runtime separately blocks the action without partial
binding publication.

An initial isolated regression exposed a test wrapper that rejected the new
optional `inputs` argument. Only that wrapper's signature was updated; all
existing shallow-copy assertions remain. The initial result (one failure,
2538 passes, one skip) is not final acceptance evidence. A pre-correction full
run was stopped and superseded by the complete final run above.

Architect acceptance: **PASS**, based on the closed independent finding, final
full and isolated regressions, approved examples and bounded evidence claims.
Required PR CI, post-merge main CI and branch cleanup remain submission gates.

## Public source review and accepted files

Sources are the approved neutral expression and public repository code. Examples
and tests use synthetic records/documents and loopback services. No private names,
paths, source data, evidence or measurements are included. MANIFESTO, BRAND,
dependencies, CI configuration and browser-support implementation are unchanged.

Accepted scope (24 files):

```text
SCENARIO.md
adapters/documents/normalizer.py
docs/onboarding.md
docs/roadmap.md
docs/tasks/response-member-references.md
docs/tasks/response-member-references-acceptance.md
examples/documents/scenarios/dictionary_document_reference.yaml
examples/documents/scenarios/locate_update_read.yaml
examples/minimal/create_locate_update_read.yaml
examples/minimal/dictionary_record_reference.yaml
refracto/contract/store.py
refracto/declaration/binding.py
refracto/declaration/expansion.py
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
tests/browser/test_response_member_references.py
tests/test_backend_resolved_bindings.py
tests/test_member_reference_consumers.py
tests/test_member_reference_documentation.py
tests/test_member_reference_inclusion.py
tests/test_response_member_references.py
tests/test_second_adapter.py
```
