# Read-only semantic object-state observation

## Authority and scope

Approved specification, 2026-10-28, starting at public main `52332e7`.
The maintainer approved the commented create/read Scenario and its observation
rules, then authorized development, independent audit and architect acceptance.
The maintainer separately authorized submission on 2026-10-29 after local
acceptance. PR checks, merge, main checks and cleanup remain publication gates.
No private workspace or product access is authorized. Public sources and synthetic examples
only; do not publish machine paths, credentials or private evidence.

Development, independent audit and local architect acceptance passed on
2026-10-28; see the [verification record](object-state-observation-acceptance.md).
The separate submission authorization is recorded above; local acceptance alone
does not claim completion of hosted delivery.

Preserve `schema_version: 1`, the do/expect structure, one-level include,
named results, users/sessions and continuation rules. No SQL, table/column names,
database type, connection configuration or business preparation scripts enter
the declaration. No transformation, branch, loop, JSONPath or R1 exception is
introduced. This task adds one bounded state assertion, not a query language.

## Approved declaration

Extend `expect.backend_state` with `object_field_equals`, requiring exactly
`object`, `id`, `field`, and `value` after `check`. `object` and `field` are
nonempty literal business names. They are not storage schema identifiers.
`id` uses an existing parameter/prior-response/named-result reference; its
resolved value must be an exact integer (not bool) or a nonempty string.
Known invalid IDs fail loading; invalid response-derived IDs block the consumer
before its action. No self-reference or new reference form is introduced.
`value` follows existing scalar-or-reference rules, resolving to a finite scalar;
null, zero, false and empty string remain distinct. Object existence is implicit
in this equality check; do not add an existence assertion in this slice.
Direct `concat` is not accepted in this new assertion's `id` or `value` position;
a reference to an already composed parameter remains valid.

The approved complete Scenario is stored in
`examples/sqlite_records/scenarios/create_and_verify_storage.yaml`, translated
to English without changing its two actions, checks or bindings. Create sends
a run-unique `code` and declared `name`, checks 201/success/observed id and stops on failure.
Read sends GET for that actual id, checks 200 and the same response id, then
checks the stored code and name through the new state assertion.

## Python boundary

Keep `StateProbe.observe(trace_id)` and `StateFacts` spans unchanged. Add a
separate `ObjectStateProbe.observe_object(query)` capability and an optional,
keyword-only `Adapters.object_state=None`. This avoids changing trace collection
or silently swallowing object queries in existing trace wrappers.

Freeze these neutral data shapes in `refracto.ports`:

- `ObjectStateQuery`: frozen, slotted, keyword-only fields `observation_id`,
  `projection`, `step_id`, `trace_id`, `user`, `session_generation`, `object`,
  `id`, `fields`. Core creates a fresh opaque observation ID per query. `fields`
  is a sorted distinct tuple of requested business names. Identity values are
  strictly typed; user/session/trace describe the actual selected execution.
- `ObservedObject`: `id` and a string-keyed `fields` dictionary of actual finite
  JSON-like observations. Missing fields remain absent; do not fill defaults.
- `ObjectStateFacts`: the echoed `query`, a nonempty `source` label, exact
  boolean `complete`, and an `objects` list of `ObservedObject` values.

The adapter never receives expected values, comparison operations, assertions,
the Scenario, all bindings or credentials through this port. Core compares the
returned facts. Query objects contain only immutable values; returned facts are
validated and deeply copied before retention. Do not create an alternate legacy
signature or pass a complete Step to simplify an implementation.

## Execution and classification

1. Resolve and validate references before the step action, including IDs used
   only by state assertions. Keep existing source attribution and blocking.
2. After the step's real response and normal response evaluation, group object
   assertions by `(object, exact ID type, ID value)`. Query each object exactly
   once, with the union of its requested fields. All its checks share that one
   snapshot. No cross-object atomic snapshot is claimed.
3. This first slice covers synchronous committed state. Do not automatically
   retry until the expected value appears. Existing span polling stays separate.
   With explicit API polling, query once after the successful terminal response;
   on timeout/FAIL/SKIP retain existing state-not-checked behavior and do not
   query. Ordinary response assertion failure does not itself suppress the
   single object observation.
4. Validate exact query echo, source, completeness, object count, ID and field
   data. Reject stale queries, another user/session/step/projection, wrong types,
   extra unrequested fields, malformed facts and non-finite/unsupported data.
   No empty or missing observation can substitute for a successful complete
   lookup. Source labels and trace correlation do not authenticate truth.

| Observation | Existing outcome |
| --- | --- |
| Complete lookup, exactly one matching object, field strictly equal | Check passes. |
| Complete lookup, no object; or requested field absent/unequal | Check FAILED. |
| More than one object, wrong identity, invalid/incomplete facts, query exception | Step ERROR. |
| Unavailable/invalid prior ID or expected-value dependency | Consumer BLOCKED before its action. |
| No object probe configured | Visible degradation; strict `status == PASSED` cannot pass. |

Literal expected null can match an actually observed null; an absent field
cannot. Preserve strict bool/int and all existing scalar comparison rules.
An observed finite object/list compared with a scalar is unequal, not coerced.
Use generic safe error text for port exceptions; SQL, driver text, paths, IDs
and observed/expected values must not leak through default representations or
new diagnostic strings.

## Projections, include and reporting

Backend and live e2e (API and request-associated UI steps) use one shared object
observation evaluator. Do not add another step loop. Frontend mock execution
never queries real storage and records these checks as outside its scope.
Contract never queries storage or treats database facts as response compatibility;
record the declared object checks as not checked there. Do not count contract
as an independent observer. Requestless state observation remains unsupported.

Existing inclusion expands references, parameters and user mappings. Exercise
an included child with the new check and a parent-provided object ID; do not
increase nesting depth. Object observations cannot be exported as named results
or referenced by later steps in this slice.

Add a keyword-only sensitive, `repr=False` `StepResult.state_observations` list.
Retain validated snapshot data, query identity and source for the step; later
adapter mutation cannot rewrite it. Preserve earlier valid observations if a
later query errors. Invalid identities are not retained as trusted observations;
report a safe ERROR instead. Well-shaped incomplete facts may be retained with
`complete=False`, but never treated as absence or successful checks. Do not add
report states, approval semantics, general serialization or a redaction system.

## Neutral SQLite consumer

Use one synthetic Records flow and a standard-library SQLite target. The normal
API commits writes before responding. The probe opens an independent read-only
connection (`mode=ro` plus `query_only`), uses fixed business-to-storage mappings
and parameterized SQL, and obtains all requested fields in one SELECT/snapshot.
It must not read from the API response, writer connection or response cache.
Database paths/configuration belong to wiring, not YAML or published evidence.
Cleanup and temporary database setup belong to the example/test harness.

Required real-storage controls: normal committed write passes; an uncommitted
write visible through the API's own connection is absent from the independent
reader and fails; committed wrong name fails; query failure errors. Confirm the
query is reached, response checks are separately recorded, calls occur after
the action, two asserted fields cause one lookup, and existing storage was not
modified by observation. This is local SQLite integration, not proof about every
database or external production service.

## Mechanical acceptance

- Loader negatives: unknown/extra/missing keys; invalid object/field names; bad
  ID literals/references/known parameter types; self/future sources; non-scalar
  expected values; unknown objects are not guessed by the adapter.
- Runtime controls: exact grouping and strict IDs, zero/one/multiple matches,
  wrong/stale query identity, missing/null/falsy fields, bool/int mismatch,
  malformed/incomplete data, query exception, missing capability, no checks/no
  query, no expected data in port inputs, and retained-snapshot mutation.
- Existing continuation, polling, include, users/sessions and default repr
  safeguards; backend/e2e parity and no frontend/contract queries. Add focused
  tests and real SQLite consumer tests, not a broad conformance platform.
- Keep the complete approved YAML runnable and document its exact consumer;
  update the existing documentation sentinel rather than bypass it.
- Full sequential suite, core-only Python 3.11/3.12, litmus, lock, hygiene and
  diff checks; independent audit by a different agent and architect acceptance.

The declaration validity, observed database state, adapter fidelity, human
approval and release decision remain distinct claims. A matching row does not
prove all causal history or durable behavior under future failures. No private
product migration, other database/cache/log channel, async consistency, writes
through the probe, Flow/UI work or submission belongs to this task.
