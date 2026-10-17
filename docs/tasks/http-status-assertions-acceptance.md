# Exact HTTP response status assertions: local acceptance

## Decision and remaining gate

**PASS** for local engineering acceptance on 2026-10-17, after specification,
development, independent audit and architect verification. The
[specification](http-status-assertions.md) defines the accepted scope. The
maintainer must still review the annotated candidate YAML before separately
authorizing submission. Nothing has been staged, committed, pushed or merged.

Starting and ending HEAD is `67ce17f8855f976d138ee84e34e2df5fdde31cbe`, equal to
local `origin/main`. The private workspace and private products were not
accessed. No deployment, business acceptance, migration, human-effort saving or
security assurance is claimed.

## Delivered capability

- `status_equals` requires one literal HTTP status; `status_in` permits an
  explicit nonempty set. Strict integers 100 through 599 only, no references,
  duplicates or multiple HTTP-status constraints in one step.
- Existing `schema_version: 1`, steps/do/expect, failure blocking, actors,
  one-level inclusion, named results and polling policies remain unchanged.
- Status is captured before normalization. Normalized status, replacement raw
  responses, input mutation or misleading fields cannot change that fact.
- Backend, explicit API e2e, associated live UI and frontend mock paths use the
  same checks. Mock evidence is not promoted into provider evidence.
- Contract independently retains the allowed set and original observed status.
  It receives protected copies for normalization. Only keys requiring exact
  status bypass normalization when that status is malformed or unavailable;
  they produce a safe mismatch. Unconstrained keys retain the previous path.
- New diagnostics do not print malformed values or response content. Existing
  sensitive-data boundaries remain; this is not universal redaction.

The complete Documents example creates with 201 and deletes with an empty 204
response. Status-only mutations preserve response bodies and normalized business
success/failure: 201 to 202, 204 to 200, and 422 to 500 are detected by the new
requirements. Four real Chromium cases separately verify mock 201 and live 200,
including misleading normalizers and failing expectations. Contract issues no
additional request and does not add an independent evidence source.

## Independent audit

The auditor did not participate in implementation and made no repository edits.
No blocking finding remains. Review covered the entire specification, changed
source, tests, examples and documentation. Five additional independent in-memory
probe groups passed:

1. Mixed exact/legacy contract entries preserve the appropriate normalization
   path per key, rather than suppressing all normalizer work.
2. Malformed status with a failing `__repr__` is neither formatted nor handed to
   a normalizer when exact evidence is required.
3. Set-based polling observes actual 202 then 204, not normalized 201; final
   contract evidence is the actual winning 204.
4. Strict integer handling rejects subclasses, floats, booleans, strings and null.
5. Live UI malformed/missing status yields ERROR followed by BLOCKED, closes
   the context, and does not expose the sensitive sentinel in details or repr.

Development also closed the malformed-contract normalizer exception path before
independent review. No general exception handling or report-state redesign was
introduced.

## Actual verification

Commands ran from the public repository, with the existing locked Python 3.12
environment unless explicitly described otherwise.

| Check | Result |
| --- | --- |
| Baseline new-feature subset | 6 representative core tests failed before implementation because vocabulary, loader and captured-status support were absent. |
| Baseline consumer suite | 14 tests failed before implementation because the new checks were unsupported. |
| Developer focused suite: `uv run pytest -q tests/test_http_status_assertions.py` | **102 passed**. |
| Developer existing relevant regression suite | **335 passed** across collection, bindings, contract, backend, e2e, normalizer and UI stepwise behavior. |
| Developer consumers: `uv run pytest -o addopts='' tests/test_http_status_consumers.py tests/demo/test_demo_http_status.py` | **18 passed**, including four actual Chromium cases, no skips. |
| Independent audit command below | **201 passed**, no skips, 35.14 seconds; five additional probe groups also passed. |
| Architect: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q` | **1337 passed**, no skips, one existing Starlette/httpx deprecation warning, 146.97 seconds. |
| Isolated editable `.[dev]` installation, Python 3.12: `python -B -m pytest -o addopts='' -q` | **1197 passed, 1 skipped**, 36.60 seconds; the optional Demo collection is skipped without its dependencies. No browser or Demo extras installed. |
| `uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/test_opensource_litmus.py` | **3 passed**. |
| `refracto validate` on maintained YAML in `scenarios`, `examples/minimal/scenarios`, `examples/documents/scenarios`, and `examples/scenario-reuse` | **18 files passed**, including the new example and existing inclusion sidecars. Authoring input-case files are not mistaken for Scenario declarations. |
| `uv lock --check`; `bash scripts/check_repository_hygiene.sh`; tracked and cached diff checks | Passed; index remains empty. New untracked files were separately checked for whitespace and public-source boundaries. |

Independent targeted command:

```sh
uv run pytest -o addopts='' -q \
  tests/test_http_status_assertions.py \
  tests/test_http_status_consumers.py \
  tests/demo/test_demo_http_status.py \
  tests/test_contract.py \
  tests/test_projection_backend.py \
  tests/test_projection_frontend.py \
  tests/test_projection_e2e_contract.py
```

Test counts overlap and must not be added together. Early consumer test mistakes
about localization tuples and stable impact paths were corrected and rerun.
One initial regression command named a nonexistent test file and exited 4; the
correct existing contract test file was then run successfully. These attempts
are not counted as successful verification. The full regression above is the
final implementation result.

## Accepted public file scope

Exactly 15 files:

- `refracto/declaration/http_status.py`
- `refracto/declaration/vocabulary.py`
- `refracto/declaration/loader.py`
- `refracto/projection/backend.py`
- `refracto/projection/ui_stepwise.py`
- `refracto/projection/contract.py`
- `refracto/contract/store.py`
- `tests/test_http_status_assertions.py`
- `tests/test_http_status_consumers.py`
- `tests/demo/test_demo_http_status.py`
- `examples/documents/scenarios/http_status_create_delete.yaml`
- `SCENARIO.md`
- `docs/tasks/http-status-assertions.md`
- `docs/tasks/http-status-assertions-acceptance.md`
- `docs/roadmap.md`

Sources are public Refract models, the public Demo and Documents reference
applications, the authorized neutral status requirement and synthetic tests.
No private names, product behavior, paths, evidence or measurements are included.
Public material is English; the maintainer's annotated review is supplied in
conversation. Hygiene automation supplements rather than replaces this source
review. MANIFESTO, BRAND, existing Scenario sources and pins, adapters, ports,
dependencies, lock and CI configuration are unchanged.

## Limits and next gate

HTTP status equality does not prove which authorization or business decision
was reached. Normalized `failure` is not a complete rejection-mechanism proof.
This task introduces neither multi-user scenarios nor continuation after failed
checks. Those require their own explicit decisions and specification.

The next action is maintainer review of the small YAML addition. Submission and
any later capability implementation require their respective authorizations;
local acceptance does not bypass those gates.
