# Committed record-state example

Run from the repository root:

```sh
uv run --frozen python -m examples.sqlite_records.run
```

The command creates and removes a temporary SQLite database. It runs the
[create/read Scenario](scenarios/create_and_verify_storage.yaml) with backend
only and exits zero only for `PASSED`. The service and API driver run in process;
this is actual SQLite integration, not a network or production-product pilot.

The target commits a new record before returning 201. Its next API request reads
that ID. A separate object probe then opens a read-only connection and reads code
and name in one SELECT. The physical names `entries`, `business_code` and `label`
stay in the target and adapter; the Scenario uses the business names `record`,
`code` and `name`. Values are bound as SQL parameters, not interpolated.

The probe receives the object identity and requested fields, never expected
values or the Scenario. Core checks its returned facts. No state is queried
repeatedly until an expectation happens to pass. One snapshot checks both fields.
The probe does not change data and cannot reuse the API writer's uncommitted
transaction. Test-only counterexamples show that an API can return 201/200 while
an independent reader sees no committed record, or sees an incorrect name.

The source label and execution identity support local attribution; they do not
certify an arbitrary adapter or prove all causal history or future durability.
Missing configuration, unavailable storage and incomplete evidence do not count
as successful business checks. The report contains sensitive observation data;
default repr suppression is not a general-purpose safe export mechanism.
