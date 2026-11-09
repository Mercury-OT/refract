# Committed record lifecycle example

Run from the repository root:

```sh
uv run --frozen python -m examples.sqlite_records.run
```

The command creates and removes a temporary SQLite database. It runs the
[create/read/delete Scenario](scenarios/create_verify_delete.yaml) with backend
only and exits zero only for `PASSED`. The service and API driver run in process;
this is actual SQLite integration, not a network or production-product pilot.

The Scenario creates a record with a run-unique code and checks 201, success and
a returned ID. It reads that exact ID, checks 200 and response identity, then
checks its committed code through a separate read-only connection. Both steps
stop on assertion failure. Finally it deletes that ID, checks 204 and requires
`object_absent` for the same ID. The physical names `entries`, `business_code` and `label`
stay in the target and adapter; the Scenario uses the business names `record`,
`code` and `name`. Values are bound as SQL parameters, not interpolated.

The probe receives the object identity and requested fields, never expected
values or the Scenario. Core checks its returned facts. The original Scenario
has no waiting policy: each step uses one observation per exact object ID.
Absence requests no fields, but still executes a real SELECT
for that ID. Zero objects proves absence in this reviewed source, one surviving
object fails the assertion, and incomplete or failed acquisition is an error.
The probe does not change data and cannot reuse the API writer's uncommitted
transaction. The [original create/read example](scenarios/create_and_verify_storage.yaml)
also demonstrates checking code and name together in one snapshot.

The pytest suite exercises backend and live e2e with real SQLite reads. Its
test-only controls include 204 without deletion, uncommitted deletion and deleting
the wrong record; all fail absence. A positive existence check catches an
always-empty probe before deletion. Incomplete facts and failed queries cannot
pass. The example command is also tested in the ordinary offline CI suite.

## Accepted asynchronous deletion

Run the separate [asynchronous Scenario](scenarios/create_verify_async_delete.yaml):

```sh
uv run --frozen python -m examples.sqlite_records.run_async
```

This target returns 202 after accepting one DELETE request. A separate worker
opens its own SQLite write connection and commits deletion later. The preceding
positive check must first confirm that the exact created ID exists. The delete
step explicitly opts in with `object_poll: {on_timeout: FAIL}`. Core repeats only
read-only observations, each on a fresh connection; it never repeats the DELETE.
The command supplies a two-second object budget and a 20-millisecond interval.
The report retains intermediate complete snapshots and records the configured
budget, observation attempts, elapsed time and final outcome. HTTP attempts
remain separate. The worker and temporary database are cleaned up on exit.

An ordinary mismatch may be retried. Incomplete facts or query errors stop
immediately; a failed response cannot be erased by a later matching snapshot.
The tests control worker scheduling from the host, not from the probe, and
cover no-op, uncommitted and wrong-ID deletions. Without the explicit policy,
the delayed target still receives only one observation and fails while present.
A second synthetic documents consumer checks string IDs and multiple field
conditions without introducing storage-specific core code.

The reader's one-second SQLite busy timeout bounds lock waits. It does not
interrupt arbitrary query execution, and the synchronous probe port cannot
cancel an arbitrary blocking adapter. Returned-late matches cannot pass and no
new read starts after the object deadline, but the deadline is not a promise of
hard cancellation. Tests exercise a real exclusive lock, error-path connection
closure and fresh reads after later commits. A match describes one complete
snapshot before the deadline, not continuous absence or future non-resurrection.

The source label and execution identity support local attribution; they do not
certify an arbitrary adapter or prove all causal history or future durability.
An adapter can lie about its identity or completeness; mapping review, positive
controls and faulty-target tests are still needed. A permission-filtered or
paginated empty view cannot establish storage absence. The observation says
nothing about other caches, replicas or backups. A soft-deleted surviving row
is present; use `object_field_equals` on its deletion flag instead. Denied
creation without a known ID needs a separately approved evidence design.
Missing configuration, unavailable storage and incomplete evidence do not count
as successful business checks. The report contains sensitive observation data;
default repr suppression is not a general-purpose safe export mechanism.
