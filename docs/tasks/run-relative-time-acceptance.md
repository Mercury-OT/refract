# Run-relative UTC time: local acceptance

Date: 2026-10-24. Result: **PASS for the bounded task**.
Specification: [run-relative UTC time parameters](run-relative-time.md).
Starting main: `50996af478d0443b37841dfc5286e4decb0deec2`.
The maintainer approved the annotated expression, time reuse and fixed-input
replay, then authorized implementation, independent audit and acceptance.
No staging, commit, push or publication is authorized. No private workspace was
accessed or modified. This record establishes local acceptance, not hosted CI.

## Accepted behavior

Direct time parameters use `from_run: time` with an optional single signed integer
offset in days, hours, minutes or seconds. Schema version 1, the existing overall
declaration and one-level pinned inclusion remain unchanged. Outputs are UTC
millisecond strings. One selected logical run captures one base; includes,
projections, polling attempts and offline contract reuse it. A day means exactly
24 hours. Numeric assertions have not acquired timestamp ordering.

The optional Python runner/binding keyword `run_time` accepts only a valid
`YYYY-MM-DDTHH:MM:SS.sssZ` string. It fixes inputs without reading the wall clock;
the existing monotonic polling clock is unchanged. Wrong types, invalid dates,
unknown units, malformed markers and overflow never fall back to a current time
or reach target actions. Symbolic validation, expansion and impact review do not
read the wall clock. Literal nested marker-looking data remains data.

RunReport explicitly retains the base, actual/fixed source and resolved direct
time parameters. These fields and the bound declaration's metadata are
keyword-only, repr-hidden and marked sensitive. Composed/business parameters
are not automatically exported. Generic serialization is not a safe export.
Unique values and concat retain their earlier behavior, including new unique
tokens during separate runs using the same fixed time.

## Consumer evidence and limits

- The Records example creates a record with the declared expiration and reads
  stored state back. Missing, null and wrong expiration evidence fails.
- The independent Documents target filters its stored timestamped records. Tests
  cover inside/outside records, exact inclusive boundaries and their one-
  millisecond neighbors, leap day and year rollover. Target preparation uses an
  explicit synthetic server clock and does not read Scenario assertions.
- The basic public query example deliberately asserts only response status and
  list length. Separate tests demonstrate that ignored filtering, empty results
  and excluded boundaries can pass those weak checks, while existing exact
  known-record checks detect them. No new temporal assertion is claimed.
- Real Chromium mock/live tests verify frozen times in UI input, outgoing
  traffic and returned evidence; altered evidence does not pass. They verify
  browser execution, not production deployment or private-product adoption.

These checks do not prove future expiration, scheduler behavior, database
independence or full-environment replay. Fixed time does not change host/server
clocks, sessions, unique tokens or persisted data. A target can correctly reject
a historical expiration. No new adapter, assertion word, port or dependency was
needed; synthetic target extensions remain in the tests.

## Actual verification

All final commands exited 0 from the public repository root.

| Check | Actual result |
| --- | --- |
| Full regression including real Chromium | 4043 passed, no skips, one existing Starlette/httpx warning; 436.86 s |
| Fresh dev-only CPython 3.11.15 | 3535 passed, one optional Demo collection skip; 43.76 s |
| Fresh dev-only CPython 3.12.13 | 3535 passed, one optional Demo collection skip; 43.24 s |
| Development declaration/runtime/include and existing value regression | 218 passed; 0.28 s |
| Stateful consumers and real Chromium time checks | 37 passed, including 14 browser cases; 11.38 s |
| Independent new-slice audit | 143 passed, including the 14 browser cases; 11.02 s |
| Independent existing value/concat, documentation and import regression | 174 passed; 0.80 s |
| Independent deterministic calendar/offset probes | 400 passed; temporary audit probes, not additional retained regression tests |
| Executable documentation and core import litmus | 49 passed; repeated successfully after recording acceptance |
| Actual CLI validate and expanded review | Both examples passed; two requests/seven response checks and one request/two response checks respectively; time nodes remained symbolic |
| Lock, hygiene, whitespace and index checks | Passed; index empty |

The initial focused declaration test failed because time markers were not
supported, before implementation. Development corrected two test-fixture issues
(an undeclared fixture parameter and YAML aliases emitted by a fixture writer).
Independent audit identified one documentation inconsistency: the old token
paragraph said any run marker generated a UUID. It now correctly says a unique
marker. No implementation repair was required by independent audit.

Full and focused checks:

```sh
PYTHONDONTWRITEBYTECODE=1 NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 \
  uv run --locked --no-sync pytest -o addopts='' -q --tb=short
PYTHONDONTWRITEBYTECODE=1 uv run --locked --no-sync pytest \
  tests/test_run_time_consumers.py tests/browser/test_run_time_parameters.py \
  -o addopts='' -q --tb=short
uv run --locked --no-sync pytest tests/test_run_time_documentation.py \
  tests/test_stabilization_documentation.py tests/test_opensource_litmus.py \
  -o addopts='' -q --tb=short
uv run --locked --no-sync refracto validate examples/minimal/create_expiring_record.yaml
uv run --locked --no-sync refracto validate examples/documents/scenarios/query_recent_documents.yaml
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Both example validation commands also ran with `--expand`; their JSON outputs
were parsed and their symbolic time parameters checked. Each fresh core
environment used a different temporary directory:

```sh
UV_PROJECT_ENVIRONMENT=<fresh-environment> uv sync --offline --locked --extra dev --python <3.11-or-3.12>
PYTHONDONTWRITEBYTECODE=1 <fresh-environment>/bin/python -m pytest \
  -o addopts='' -q -rs --tb=short -o cache_dir=<fresh-cache> --basetemp <fresh-test-directory>
```

Both environments imported this checkout's core and lacked httpx, Playwright,
Starlette, uvicorn, FastAPI and OpenTelemetry. Their sole skip was the optional
Demo collection gate for absent httpx; it does not replace browser evidence.

## Independent audit and architect acceptance

Independent audit: **PASS**, no unresolved findings. It reviewed all changed and
new implementation, tests, specification and examples; ran the focused commands
above; and independently probed calendar/offset arithmetic without clock access.
It verified the literal-data boundary, scopes, named results, pins, fixed replay,
sensitivity, absence of fallback and truthful consumer claims. The reviewer did
not edit files or access private sources.

Architect acceptance: **PASS**, supported by full and isolated regression,
actual CLI checks, audit evidence and public-source review. Sources remain the
approved neutral requirements and existing public synthetic examples. No private
names, paths, data or measurements are included. Vocabulary, ports, existing
adapters, polling clock, dependencies, CI, MANIFESTO and BRAND are unchanged.
The public branch remains main at the starting commit; changes are unstaged.
Submission still requires a separate maintainer instruction.

Accepted scope (24 files):

```text
SCENARIO.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/run-relative-time.md
docs/tasks/run-relative-time-acceptance.md
examples/documents/scenarios/query_recent_documents.yaml
examples/minimal/create_expiring_record.yaml
refracto/declaration/binding.py
refracto/declaration/expansion.py
refracto/declaration/field_comparison.py
refracto/declaration/impact.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/declaration/run_values.py
refracto/declaration/values.py
refracto/report.py
refracto/runner.py
tests/browser/test_run_time_parameters.py
tests/test_run_time_consumers.py
tests/test_run_time_declaration.py
tests/test_run_time_documentation.py
tests/test_run_time_inclusion.py
tests/test_run_time_runtime.py
tests/test_stabilization_documentation.py
```

## Subsequent submission authorization: 2026-10-24

After reviewing and accepting this completed task, the maintainer separately
authorized submission of exactly the 24 files listed above: create a dedicated
public task branch, commit and push it, open a pull request, merge only after
green PR checks, verify the merged main CI, then remove both task branches and
synchronize a clean local main. The private workspace remains untouched.

The earlier no-submission statements describe the local acceptance stage and
remain historical. This later instruction authorizes publication of the accepted
scope only. It does not authorize the next task, any new expression, or expanded
implementation. Hosted CI and merge outcomes are established by the resulting
pull request and workflow records, not by this pre-submission acceptance record.
