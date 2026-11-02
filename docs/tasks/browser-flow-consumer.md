# Runnable browser Flow consumer

Status: scope and the four declarations were approved by the maintainer on
2026-11-02. Development, independent audit and architect acceptance precede the
authorized task-branch submission, green PR/main checks, merge and cleanup.
Baseline public main: `522e030`.

## Purpose and limits

Deliver one runnable live e2e Flow: create a record through a page, update that
same record, then read it and verify both the response and displayed result.
Browser Flow execution already exists. This is a bounded integration example,
not a new execution capability, adoption study or general stabilization task.

Reuse the existing `examples/browser_multi_origin` synthetic application, API,
and its `promise` and `async` frontends without changing their source. Those are
two frontend implementations of one synthetic product, not independent products.
Its existing page exposes name, code and record-ID inputs, action buttons and a
JSON result display. Do not add test attributes, repair the page or replace a UI
action with another HTTP client.

The only new adapter observation reads the actual displayed business result.
Reuse current browser support, authentication, response normalization and logical
request mapping. No core, browser-support, port, vocabulary, dependency, CI or
existing target changes are planned. If execution exposes a defect requiring
such a change, report it before expanding scope. Keep schema_version 1 and
one-level include. No editor, Flow branches, cleanup semantics, storage assertion,
object_absent, private product, private evidence or workroom access.

Public sources are existing public code and the approved neutral example. New
repository prose and comments are English. No private names or paths, including
in filters, source inventories, commit text or test data.

## Approved declarations

The approved four-document example is materialized under `examples/browser_flow/`:

- `browser.flow.yaml`: Flow `records.browser_lifecycle`, user `creator`, stop on
  a non-passing Scenario, and three invocations `create`, `update`, `read`.
  Each maps child `operator` to `creator`.
- `create.yaml`: `records.browser_create`; local `code: {from_run: unique}`;
  open `records.page`, fill `name` and `code`, click `create`. Check the actual
  POST to `[records-api, records]`, 201, success, ID presence, intended name/code
  and displayed name/code matching counts. Publish observed `record_id` and
  independently declared `record_code` only after success.
- `update.yaml`: `records.browser_update`; fill `record_id` from Flow, fill
  `name` from `updated_name`, click `update`. Check actual PATCH to the same ID,
  200, success, response ID/name and displayed identified record name. Publish
  `expected_name` from the already declared `updated_name`, never from the
  response being judged.
- `read.yaml`: `records.browser_read`; click `read` without another open or ID
  fill. Check actual GET, 200, success, same response ID/name/code and displayed
  identified record name.

Flow `record_id` and `record_code` start unset. `expected_name` starts as
`Initial record`; `updated_name` is `Updated record`. Existing `from_flow`,
`write_flow`, user mapping and fingerprint sidecar rules apply unchanged.
Preserve the approved actions, order, expectations, inputs and publication rules.
Add the normal `.scenarios.json` byte pins; pins identify content, not approval.
Keep existing examples and their historical declarations untouched.

## Observation and execution boundary

`records.result` means the actual page result display. Read the DOM text of the
existing result element and interpret its displayed data, not a stored HTTP
response, expected ID, expected value, Scenario or parameter store. Empty display
before an operation is distinct from malformed or unavailable observation.
Missing business identity must not be synthesized; unsupported display shapes
cannot become a fabricated matching object. A duplicate display/ambiguous mapping
must not silently select the first object. No mutation of source observations.

Only the first Scenario opens the page. The same mapped user's existing browser
context and session continue through update and read. Read uses the actual ID
input left by update; its request must agree with the Flow's observed identity.
No implicit navigation, filling, focus repair, session recreation or retry is
allowed. The complete eight-action sequence is open/fill/fill/click,
fill/fill/click, click. The actual business requests are POST/PATCH/GET.

The public entry point runs both frontend implementations using only live e2e,
and returns nonzero unless each Flow is strictly PASSED. Preserve native
Flow/Scenario/Step/check results instead of reconstructing a passing report.
Display a bounded summary with no credentials, raw parameter history, response
bodies or raw exception messages. Runtime values remain available in memory for
explicit verification, not automatic publication.

Response and displayed content are different observation channels, but both
originate in this application; this is not independent database evidence. Sample
mapping tests guard mistakes, not adversarial same-process adapter code. Reuse the
existing threat model; no new trust or approval mechanism.

## Verification matrix

1. Validate the four approved files and exact sidecar; verify their authored
   semantics and the existing one-level/schema-version boundaries. Flow-dependent
   Scenarios remain invalid as standalone declarations.
2. Freeze the unchanged target's app.py/promise.js/async.js hashes, and verify them
   before and after every actual consumer run. No normal-target source mutation.
3. Both implementations must run the actual eight actions and three business
   requests, obtain the same observed ID across nodes, use one named session and
   one browser context, navigate once, and close owned resources once.
4. Page observations must independently reflect actual DOM text. Exercise empty,
   malformed, missing-field/identity and ambiguous display samples. A changed
   response alone cannot fill in missing rendering. Keep strict value types.
5. Labeled isolated fault: HTTP response is correct while displayed content is
   wrong. The applicable UI check must fail; native non-PASSED results remain.
6. Labeled isolated fault: update returns an apparently correct acknowledgement
   but does not persist the intended value. Final actual read must fail against
   the independently declared intended value, not learn an expected value from
   the stale response.
7. Missing creation ID cannot publish a valid destination or run a later action
   using a guessed ID. A failed update cannot publish/reuse old expected_name;
   default stop blocks later nodes. A separately labeled continue control must
   preserve invalidation and dependency blocking rather than restoring stale data.
8. Failure controls are in isolated test instances/in-memory fault fixtures;
   production example sources and approved expectations do not change. Verify
   real server calls and DOM, not merely monkeypatched core reports/evaluators.
9. Entry-point failure propagation and value-safe output; repeated runs do not
   reuse unique values, sessions or prior result identity. Preserve both successes
   and failures. No pass is claimed for an unexecuted browser test.
10. Run the focused consumer tests, existing browser-consumer regression, full
    guarded suite, dev-only core collection, litmus, lock, hygiene and diff checks.
    Independent audit must inspect expectation ownership, target immutability,
    fault discovery, context continuity and truthful report/exit behavior.

Record actual commands/results, the fixed test matrix and any residual. Count
new adapter observation/mapping code only as descriptive size, not a measured
maintenance or review-cost improvement. Stop after this consumer; further gaps
need a separate task decision.

## Deliverables

The four YAML files and sidecar, a narrow example adapter/runner and README,
target-source hashes, focused tests, this specification, a factual acceptance
record and roadmap/link updates. Record the preceding Flow delivery through
PR #47/main `522e030` without rewriting its historical local verification.
No new YAML, core or browser-support feature is authorized by this task.
