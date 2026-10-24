# Run values and bounded string composition: acceptance

The 2026-10-22 record below is historical. See the
[resumed verification](#resumed-verification-2026-10-24) for the current baseline
and renewed maintainer authorization. Neither record authorizes submission.

Date: 2026-10-22. Result: **PASS for the bounded task**.
Specification: [run values and composition](run-values-concat.md).
Starting main: `14a7f88a5f293bae7d37560a9798c1c04ff23e36`.
The maintainer approved the expression and implementation. No submission is
authorized; all task changes remain unstaged, uncommitted and unpushed.
No private workspace or product was accessed or changed.

## Delivered behavior

- A direct parameter may declare `{from_run: unique}`. A selected top-level run
  binds one UUID4 hex token on an independent copy. Repeated/concurrent runs do
  not mutate the loaded declaration or share generated values.
- `concat` joins a nonempty sequence of strings and existing references. Literal
  strings can appear anywhere; prefix/suffix fields, nested concat syntax,
  coercion, arithmetic and general expressions are not accepted.
- Parameter dependencies are checked without generation. Response operands use
  actual earlier observations, including dictionary keys, unique list members
  and named results. Missing or invalid operands block the consumer atomically
  before action and preserve the responsible source-step identity.
- Included defaults retain their scope. Caller overrides affect derived defaults,
  including structured dictionary/list arguments. Typed nodes are evaluated;
  ordinary dictionaries and response data are not reparsed as declarations.
- Backend, mock/live UI, API e2e, polling and contract share the frozen values and
  existing preparation rules. Low-level projections reject unbound run markers
  before authentication/action rather than inventing their own token.
- The report exposes `run_unique` explicitly, hidden from default repr and marked
  sensitive. Authoring expansion remains symbolic and refuses already-bound run
  models. Generic report serialization is not asserted to be a safe export.

Format 1, one-level inclusion, named results, users, sessions and assertion
vocabulary are retained. No adapter, port or dependency change was needed.

## Verification

Commands ran from the public repository root. All final gates below completed
successfully; these are local results, not hosted CI or submission evidence.

| Check | Result |
| --- | --- |
| `uv run --locked --no-sync pytest --basetemp <fresh temporary directory> -o addopts='' -q --tb=short` | 3880 passed, real Chromium, no skips, one existing Starlette/httpx warning; 426.83 s |
| Isolated dev-only Python 3.11: `python -m pytest --basetemp <fresh temporary directory> -o addopts='' -q --tb=short` | 3392 passed, one optional Demo collection skip, 40.22 s |
| Isolated dev-only Python 3.12: same command | 3392 passed, one optional Demo collection skip, 40.13 s |
| New declaration, dependencies, runtime, consumers, documentation and browser tests plus the updated documentation inventory | 183 passed, 9.65 s; 12 real Chromium cases included |
| Final documentation fragment/inventory check | 44 passed, 0.45 s |
| Independent audit regression | 435 passed |
| Independent real Chromium positive mock/live checks | 2 passed, 10 intentionally deselected; no skip |
| Core import litmus | 3 passed |
| CLI validation of both new examples | Both load: three requests and ten response checks each |
| CLI expanded Documents review | Symbolic run-value and concat nodes; no token generated |
| `uv lock --check`, repository hygiene, diff and cached-diff checks | Passed; index empty |

The two isolated environments were existing dev-only installations, not fresh
installs. Their Python versions and imports were checked: Playwright, httpx,
Starlette and uvicorn were absent. The optional Demo skip does not stand in for
the real browser tests.

The Documents and independently implemented Records examples run against their
synthetic target services. Tests keep old objects and perform three successful
top-level executions, checking fresh names, actual query values and the newly
observed identifiers. Duplicate matches, missing matches, missing keys and
malformed members cannot pass. These are synthetic capability tests, not proof
of private-product adoption or maintenance savings.

## Independent audit and corrections

Independent audit: **PASS**, with no unresolved findings. The reviewer did not
write files. Two independently reproduced findings were corrected and retested:

1. An already-bound model could be passed to authoring expansion and reveal the
   generated token as a literal. Bound models are now explicitly rejected; the
   original symbolic declaration remains reviewable.
2. Structured include arguments could contain compiled nodes that were not
   frozen. Binding and the unbound guard now traverse dictionary/list values,
   processing typed nodes only. Six regression cases failed before the fix and
   passed after it; independent backend/contract probes also passed.

Development checks also caught imprecise source attribution for a bad concat
operand and missing inventory entries for the new documentation fragments.
Both were corrected without weakening assertions or ignoring documentation.
Shared parameter-dependency analysis is memoized to avoid repeated traversal;
a 44-level symbolic dependency test covers this property.

Architect acceptance: **PASS**. The independent findings are closed, actual
browser and isolated-core gates pass, and the accepted scope is listed below.
Public main and local origin/main remain at the starting revision. No branch,
commit, push, PR or merge was created. Submission still needs a separate explicit
maintainer instruction; hosted PR/main CI and cleanup have not been attempted.

## Limits retained

"Bounded" describes the available operations, not an output-size quota. Large
compositions still consume host memory; no general resource sandbox is claimed.
UUID4 is not a proof of absolute collision impossibility. The token is not a
server ID, an environment isolation mechanism, cleanup, or a set of independently
generated random variables. Multiple writing projections using shared target
storage still require host-managed isolation. Contract rechecks actual retained
provider evidence but does not add an independent observer. Relative time and
external parameter overrides remain separate, unimplemented tasks.

## Public scope

Only public code, the maintainer-approved neutral expression and synthetic
Records/Documents/browser fixtures were used. New files were reviewed separately
from tracked-file hygiene. No private names, paths, product data or evidence were
copied. Assertion vocabulary, dependencies, CI, MANIFESTO, BRAND and archived
measurement artifacts remain unchanged.

Accepted files (28):

```text
SCENARIO.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/run-values-concat.md
docs/tasks/run-values-concat-acceptance.md
examples/documents/scenarios/run_unique_create_locate_read.yaml
examples/minimal/run_unique_create_locate_read.yaml
refracto/declaration/binding.py
refracto/declaration/expansion.py
refracto/declaration/field_comparison.py
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/declaration/run_values.py
refracto/declaration/values.py
refracto/projection/backend.py
refracto/projection/contract.py
refracto/projection/ui_stepwise.py
refracto/report.py
refracto/runner.py
tests/browser/test_run_values_concat.py
tests/test_concat_dependencies.py
tests/test_run_value_consumers.py
tests/test_run_values_declaration.py
tests/test_run_values_documentation.py
tests/test_run_values_runtime.py
tests/test_stabilization_documentation.py
```

## Resumed verification: 2026-10-24

The maintainer reconfirmed the same expression and authorized verification of
the preserved implementation, independent audit and architect acceptance, not
redevelopment or expanded scope. Current public main and local origin/main are
`ac71abf3e8a9efd3e1d70e389cedc042ab1e230a`, including the separately delivered
two-path reuse task. All 28 files listed above were already present as local
changes at the start of this resumed task. They were not regenerated.

The current checks reuse the existing source, test assets and synthetic
Records/Documents consumers. Those consumers exercise actual state changes in
in-process synthetic targets, not private-product or production deployment
evidence. Browser coverage comes from the full suite's real Chromium tests.

### Current check results

| Check | Result |
| --- | --- |
| Full regression with real Chromium | 3898 passed, no skips, one existing Starlette/httpx deprecation warning; 430.12 s. |
| Fresh isolated dev-only CPython 3.11.15 | 3404 passed, 1 optional Demo collection skip, no warnings; 39.47 s. |
| Fresh isolated dev-only CPython 3.12.13 | 3404 passed, 1 optional Demo collection skip, no warnings; 39.27 s. |
| Independent focused implementation audit | 127 tests passed; no reproducible blocker. |
| Independent temporary combined probes | 14 scope, selector, invalid-evidence and isolation checks passed; not additional retained regression tests. |
| Failing-run default report representation | Generated token remained hidden. |
| Focused real Chromium run-value/concat checks | 12 passed, no skips; 9.18 s. |
| Executable documentation and core import litmus | 47 passed; final post-record rerun 0.48 s. |
| Both create/locate/read examples | CLI validation passed: three requests and ten response checks each. |
| Documents expanded review | Valid JSON with symbolic run-value/concat nodes, no generated token. |
| Lock, hygiene, public-source inspection and diff/index checks | Passed; index empty. |

Each fresh core environment was created using a separate temporary directory
and the locked dev-only dependency selection:

```sh
UV_PROJECT_ENVIRONMENT=<fresh-environment> uv sync --offline --locked --extra dev --python <3.11-or-3.12>
PYTHONDONTWRITEBYTECODE=1 <fresh-environment>/bin/python -m pytest \
  --basetemp <fresh-test-directory> -o cache_dir=<fresh-cache-directory> \
  -o addopts='' -q -rs --tb=short
```

Both environments used pytest 9.1.1 and PyYAML 6.0.3, imported this checkout's
core, and lacked httpx, Playwright, Starlette, uvicorn, FastAPI and OpenTelemetry.
The sole reported skip was the optional Demo collection gate for absent httpx.
This isolation check does not replace browser execution.

The full and focused commands ran from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --locked --no-sync pytest \
  --basetemp <fresh-full-test-directory> -o addopts='' -q --tb=short
PYTHONDONTWRITEBYTECODE=1 uv run --locked --no-sync pytest \
  tests/browser/test_run_values_concat.py \
  --basetemp <fresh-browser-test-directory> -o addopts='' -q --tb=short
PYTHONDONTWRITEBYTECODE=1 uv run --locked --no-sync pytest \
  tests/test_run_values_documentation.py tests/test_stabilization_documentation.py \
  tests/test_opensource_litmus.py -o addopts='' -q --tb=short
```

The independent 127-test command was:

```sh
uv run --locked --no-sync pytest --basetemp <fresh-audit-directory> \
  -o addopts='' -q --tb=short tests/test_run_values_declaration.py \
  tests/test_run_values_runtime.py tests/test_concat_dependencies.py \
  tests/test_run_value_consumers.py
```

All commands exited 0. The fourteen additional checks ran as a temporary inline
audit probe; no new probe script or regression test file was added to the repository.

Independent audit found no required source repair. It rechecked one-token run
scope, repeated/concurrent declaration isolation, include overrides and derived
defaults, actual-response dependencies, strict operand types, literal data,
symbolic review and default-report sensitivity. Temporary probes additionally
combined these mechanisms rather than changing the approved contract.

Final independent audit and architect acceptance: **PASS**. Existing functionality
was reused without a source repair, test rewrite or expression change. Of the
349 tracked/untracked repository files captured at resumption, 346 remain
byte-identical; only this specification's authorization, this acceptance record
and the roadmap status were updated. The task still has the same 28 uncommitted
files, no additional file scope, and an empty index. Assertion vocabulary,
adapters, ports, dependencies, CI and previously delivered examples are unchanged.

The limits recorded above still apply: no absolute uniqueness, target isolation,
automatic cleanup, relative-time values, multiple independent random generators,
deeper inclusion or general expression language is claimed. No private workspace
or product has been accessed. No staging, commit, push, branch, PR or merge is
authorized or performed in this resumed task. Submission remains a separate
maintainer decision after review of this current acceptance.

## Subsequent submission authorization: 2026-10-24

After the resumed independent audit and architect acceptance, the maintainer
accepted this task and explicitly assigned its separate public submission:
dedicated task branch, commit and push, pull request, successful required checks,
merge, successful main CI and branch cleanup. Scope is exactly the 28 files
listed above, including this authorization and the roadmap delivery status.
The preceding local-acceptance statements remain historical; no implementation
or test behavior is changed by this submission authorization. No private
workspace operation or private publication is authorized. The next-task request
is limited to a recommendation, not implementation.
