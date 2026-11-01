# Ordered Flow: verification and acceptance

Date: 2026-11-01. Starting public main: `5015e45`.
Specification: [ordered Scenario Flow](scenario-flow.md).
Status: implementation, two independent audits, complete regression and architect
acceptance passed. Submission is authorized; this local acceptance record does
not claim that a commit, PR, merge or hosted CI has already completed.

## Maintainer summary

- One ordered Flow retains mapped users' sessions and pages across Scenarios.
- Explicit shared reads use entry snapshots; verified writes publish atomically.
- Failed writers invalidate their destinations instead of reusing stale values.
- Reports preserve Flow, Scenario and step identity with sensitive value history.
- No new assertions, nested Flow, branching, editor or automatic cleanup is added.

## Scope and consumer evidence

The public four-document [example](../../examples/flow/README.md) uses the existing
Documents adapter and in-process REST application unchanged. It creates a document,
modifies content, then reads the same observed ID. All three actual operations use
one session. Content replaces the proposed record-name example field solely to
reuse the existing synthetic target; the approved declaration and value-copying
semantics are unchanged. This is not a private-product or deployment acceptance.

The example checks update against independently declared intended content before
publishing that intended value. A labeled stale normalized observation makes both
stop and continue runs non-PASSED. No read request is sent using the invalidated
old expected content. Actual response bytes are not rewritten by that fault.
Repeated Flow runs retain separate sessions, IDs and parameter versions.

Real Chromium tests cover frontend and e2e. A first Scenario opens and fills named
and anonymous pages; a later Scenario operates the retained DOM without reopening
or filling it again. The tests check actual live requests or the shared mock queue,
Flow reads/writes, per-user contexts and exactly-once closure. Mock evidence is not
live backend evidence, and contract reuses backend evidence rather than providing
another independent observation channel.

## Findings corrected before acceptance

1. Independent runtime review found that replacing an available Flow reference
   with its value lost dependency provenance. A wrong-type dynamic path value was
   ERROR and stopped independent work. Frozen Flow input-source metadata now keeps
   it consumer-local BLOCKED, including aliases and concat. Contract replays the
   same dependency outcome. The independent probe and regression were rerun.
2. Both independent auditors reproduced a generated binding-name collision with
   valid colon-containing invocation/field names. Execution-local bindings remained
   separate, but expansion attributed a reference to a later foreign Scenario.
   Length-prefixed invocation identities remove that ambiguity. The exact
   collision regression and independent reproduction now pass.
3. Developer peer review corrected duplicated preflight results across nodes and
   lost generic frontend mock diagnostics. It also preserved final UI close errors
   without rewriting earlier successful step evidence.
4. Continued Flow execution exposed implicit authentication retry after a failed
   acquisition or replacement. Failed authentication is now unavailable until an
   explicitly requested new session; it cannot silently reuse the old session.

## Independent review

The runtime/whole-change auditor reviewed frozen snapshots, publication,
invalidation, session continuity, UI evidence, contract replay, source pins,
reporting and the public consumer. Its final focused run passed 323 tests. Both
reported defects were independently reprobed after correction; no unresolved
finding remained.

The separate declaration auditor passed 80 maintained declaration tests and 14
independent temporary adversarial cases. Those covered transitive child tampering
and attempted repinning, repeated invocation provenance, literal marker-looking
data, null/unset/empty distinction, forbidden write sources, standalone rejection
and the exact expanded-leaf limit. It confirmed the binding-name correction.
Neither auditor edited repository files or accessed private material.

## Reproducible checks

Commands run from the public repository root:

```sh
uv run --locked --no-sync refracto validate-flow examples/flow/document_lifecycle.flow.yaml
uv run --locked --no-sync refracto validate-flow examples/flow/document_lifecycle.flow.yaml --expand
uv run --locked --no-sync python -B -m examples.flow.run_example
uv run --locked --no-sync python -B -m pytest -q tests/test_flow_examples.py tests/test_opensource_litmus.py
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

The public example returned PASSED; the consumer/litmus selection passed 11 tests.
Guarded real-browser Flow tests passed both cases with exit 0 and complete cleanup.
The lock, hygiene and diff checks passed. The vocabulary file is unchanged.

Two isolated dev-only environments ran the complete core collection with the
standard test guard and a 600-second suite budget: Python 3.11.15 executed 4552
tests with exit 0 in 43.77 seconds; Python 3.12.13 executed 4552 tests with exit 0
in 42.31 seconds. Both had final progress, complete owned-group cleanup and no
cleanup errors. Optional browser/demo dependency collection remains separate.

Full regression command:

```sh
uv run --locked --no-sync python scripts/run_tests.py --output-dir <new-local-evidence-directory> -- -q
```

The complete unfiltered suite executed 5603 tests with exit 0 in 934.15 seconds,
including real Chromium and Demo tests. One existing Starlette/httpx dependency
warning remained. The guard recorded final progress, no timeout or diagnostic
request, complete owned-group cleanup and no cleanup errors. The 385-file
executable-source freeze remained unchanged through verification. New documentation
and acceptance status were reviewed separately for English-only neutral content,
working links, no local machine paths and no private source information.

The final tracked-file hygiene check then rejected a negative-test URI using a
non-allowlisted documentation host. It was replaced with the allowed example.com
host without changing the rejection test's meaning or any production code. The
80-test declaration suite and tracked-file hygiene passed again before push.

## Limits and delivery boundary

Only linear ordering is implemented. All non-PASSED results remain non-PASSED;
strict gating uses `status == "PASSED"`, not the legacy `.passed` convenience
property, which includes DEGRADED. Continue does not guarantee the next operation
has usable evidence, session or application state. Publication is not a target
transaction and does not roll back effects.

Source hashes identify bytes, not approval. Default representations hide shared
values; arbitrary serialization is not a safe publication mechanism. The bounded
in-process threat model is unchanged. No benchmark, adoption benefit or human
review-cost improvement was measured. Object absence remains paused.

No private workroom, product or private evidence was accessed or changed. All
public material uses neutral examples; no private information was added to CI
filters. Submission must still use a dedicated branch, passing required PR checks,
passing post-merge main CI and branch cleanup.
