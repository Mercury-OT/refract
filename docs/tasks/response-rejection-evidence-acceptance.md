# Response-based rejection evidence: local acceptance

Date: 2026-10-17. Result: **PASS for the bounded task**.
Specification: [response-based rejection evidence](response-rejection-evidence.md).
Starting and acceptance HEAD: `b2fdab2bc1092433eef0baa684c44cefbf665a97`.
The maintainer approved the example and evidence boundary before implementation
and explicitly authorized public submission after audit and acceptance. This
record captures local acceptance, not a claim that submission or hosted CI has
already completed. The task PR records those later delivery gates.

## Accepted result

The new `documents.owner_access` example preserves the approved four steps:
creation, creator read, peer profile check, and peer read of the same observed
document ID. The last step requires actual status 403, normalized failure, and
the target's explicit `owner_required` code. Preparation failures stop the flow;
the peer's existing session is reused rather than silently refreshed.

There is no new rejection vocabulary or state, no format change, and no runtime
implementation change. Format 1, users, one-level inclusion, named results, ports,
reference adapters, target behavior, and contract execution remain unchanged.
The older owner/peer example and historical acceptance records are preserved.

Tests establish the following bounded distinctions through the real public
Documents loader, runner, transport, normalizer, and synthetic application:

- A revoked token before the profile check fails that prerequisite and blocks
  the final read. Revocation after a successful profile is exposed by the actual
  final 401 without reauthentication.
- A test-injected missing creation title reaches the target's real validation,
  returns 400/title_required, and blocks later permission checks.
- Missing, null, unknown, wrong-type, authentication, validation, and other
  authorization reasons cannot satisfy ownership evidence even with unchanged
  403 and normalized failure. The expected reason remains a passing neighbor.
- A temporary weaker declaration removing only the reason check passes an
  ambiguous 403 that the approved declaration rejects. The maintained example
  is not weakened. Each final-response mutation checks successful prerequisites
  and actual fault reachability rather than counting unrelated failures.
- Real execution errors, missing state capability, empty state observations,
  probe exceptions, and sensitive default representations retain existing
  behavior. No missing evidence is relabeled as a native UNVERIFIED state.

Both backend plus contract and explicit-API e2e execute these controls. The latter
is not browser evidence. Contract shares backend recordings and normalization;
it is not an independent decision witness. A response code remains the target's
stated reason, not proof that its internal authorization decision was correct.
No real-product adoption, security detection rate, or review-cost benefit is
claimed. The stronger assertion, not a new framework mechanism, explains the
bounded weak/strong comparison.

## Actual verification

Commands ran from the public repository root and exited 0 unless noted below.

| Check | Result |
| --- | --- |
| `uv run pytest tests/test_rejection_evidence.py` | 57 passed |
| New tests plus Documents users/session and continuation tests | 79 passed |
| Independent focused command below | 220 passed |
| Independent additional in-memory target-output probes | 16/16 passed |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 1605 passed, 1 existing Starlette/httpx warning, no skips; 149.85 s |
| `"$TASK_CORE_ENV/bin/python" -B -m pytest -o addopts='' -q --tb=short` | 1458 passed, 1 optional Demo collection skip; 36.36 s |
| `uv run --locked --no-sync pytest tests/test_scenario_contract_doc.py tests/test_include_documentation.py tests/test_minimal_onboarding.py tests/test_opensource_litmus.py -o addopts='' -q` | 24 passed |
| `uv run --locked --no-sync refracto validate examples/documents/scenarios/owner_access.yaml` | 4 steps, 4 requests, 12 response assertions |
| Maintained Scenario loading | 24 files passed |
| `uv lock --check` | passed, lock unchanged |
| `bash scripts/check_repository_hygiene.sh` | passed |
| `git diff --check` and `git diff --cached --check` | passed; index empty at acceptance |

`TASK_CORE_ENV` is a fresh Python 3.12 editable `.[dev]` environment. Playwright,
FastAPI, httpx, and uvicorn were confirmed absent. Its optional collection skip
does not replace the full suite's actual browser execution.

Independent audit command:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider \
  tests/test_rejection_evidence.py tests/test_documents_users_sessions.py \
  tests/test_documents_failure_continuation.py tests/test_http_status_consumers.py \
  tests/test_http_status_assertions.py tests/test_report.py \
  tests/test_opensource_litmus.py tests/test_include_documentation.py
```

The additional audit probes used eight bounded target-output variants across
both execution combinations: a wrong positive-read document ID; the correct
ownership reason with status 401 or 200; trailing whitespace; changed case;
a nested reason; a scalar fault envelope; and a reason array. Final-response
probes required three passing prerequisites, four requests, two authentications,
and the unchanged peer session. The wrong positive ID stopped after two requests.
These were temporary in-memory checks, not additional committed tests.

An initial overbroad declaration-discovery command included authoring
`*.case.yaml` inputs, which use a different schema, and failed. The corrected
command loaded the explicit Scenario roots: `scenarios`,
`examples/minimal/scenarios`, `examples/documents/scenarios`, and
`examples/scenario-reuse`. No historical input was rewritten or silently
converted. This command correction was not an implementation defect.

## Accepted public file scope and source review

```text
SCENARIO.md
docs/roadmap.md
docs/rejection-evidence.md
docs/tasks/response-rejection-evidence.md
docs/tasks/response-rejection-evidence-acceptance.md
examples/documents/scenarios/owner_access.yaml
tests/test_rejection_evidence.py
```

Independent audit and architect review found no remaining blocker. All public
material derives from the public Documents target, existing Refract semantics,
and the explicitly approved neutral scenario. New files were reviewed as well
as tracked diffs; hygiene is supplementary, not a proof of neutrality. Core,
adapters, reference application, CI, dependencies, MANIFESTO, and BRAND have no
changes. No private workspace was read or changed, and no private evidence or
names were used. No staging or submission occurred before acceptance.
