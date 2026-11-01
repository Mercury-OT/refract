# Ordered Scenario Flows

A Flow runs several named Scenarios in order as one business execution. It keeps
each mapped user's session and browser context between Scenarios and provides
explicit shared parameters. A successful earlier Scenario can establish system
state for a later one, even when no parameter passes between them. Passing checks
does not prove every implicit prerequisite or the whole business intent.

The executable format remains `schema_version: 1`. Scenario actions, assertions
and one-level inclusion retain their existing contract in [SCENARIO.md](SCENARIO.md).
There is no branching, parallel execution, nested Flow, automatic cleanup or
arbitrary script action. Flow is not an extra level of recursive include.

## Complete runnable example

The [Flow](examples/flow/document_lifecycle.flow.yaml) schedules
[creation](examples/flow/create_document.yaml),
[update](examples/flow/update_document.yaml) and
[read-back](examples/flow/read_document.yaml). It uses the existing synthetic
Documents target and adapter without modifying their behavior. The target uses
an actual ownership/session store and an in-process REST transport; this example
does not claim a network deployment or real-product acceptance.

From the repository root:

```sh
uv run --locked --no-sync refracto validate-flow examples/flow/document_lifecycle.flow.yaml
uv run --locked --no-sync refracto validate-flow examples/flow/document_lifecycle.flow.yaml --expand
uv run --locked --no-sync python -m examples.flow.run_example
```

The last command uses backend plus contract and requires strict `PASSED`. It
expects three real target operations with one authentication. Contract checks
the same provider evidence, not an independent data source. A standalone
`refracto validate` of one of these Flow-dependent Scenarios intentionally fails.

## Flow document

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`. |
| `flow` | Stable Flow identifier. |
| `description` | Optional human-readable intent. |
| `users` | Distinct logical users, including reserved `anonymous` when needed. |
| `on_failure` | `stop` by default, or explicit `continue`, between Scenarios. |
| `parameters` | Shared parameter declarations, optionally initialized. |
| `scenarios` | Nonempty ordered invocation list. |

An invocation has its own `id`, a literal `scenario` ID and explicit `with_users`
mapping of that Scenario's participants to Flow participants. Repeated calls to
the same Scenario have different invocation IDs. The list contains no operation
or expectation overrides. Users retain the existing distinct-account and
anonymous-mapping restrictions; credentials are supplied by the host adapter.

The companion `.scenarios.json` file pins every scheduled Scenario by relative
local path and raw SHA-256. A scheduled Scenario containing includes also pins
its `.includes.json` sidecar using `includes_sha256`; the latter pins child files.
The full closure is checked before execution. Paths cannot escape the Flow
directory or traverse symlinks. A fingerprint confirms content identity, not human
approval. Changed source or wiring still needs review.

## Shared parameters

Flow parameters use uniform declaration objects. An empty object declares an
unset parameter; `initial` supplies a finite JSON-like value. An initial null,
false, zero, empty string, empty list or empty object is an actual value, not an
unset marker. There are no mandatory type fields and no implicit conversions.
Initial data does not introduce another expression or generator language.

`from_flow` reads the parameter namespace owned by this Flow execution.
`from_parameter` continues to read Scenario-local parameters. Names are not
implicitly inherited or overwritten. Reads use a deep snapshot taken when the
Scenario starts; later writes cannot rewrite the expected value of an already
executing assertion. Within a Scenario, use existing `from_step` references for
newly observed responses.

A scheduled Scenario's top-level `write_flow` explicitly names each destination
and its copied source: an observed `from_step` / `response_field`, an included
named result, `from_parameter`, or `from_flow`. It performs no arithmetic,
formatting, defaulting, expression evaluation or assertion-driven repair.

In the example, creation publishes the actual `document_id`. Update verifies
the response against the declared `updated_content`, then copies that intended
value into `content`. Read-back checks the same ID and intended content. It does
not learn its expected content from the response it is meant to judge.

All sources must resolve and the Scenario must strictly pass before the write
set is published atomically. A failed publication is visible and prevents success.
Repeated explicit writes overwrite the destination. If a Scenario fails, every
destination it declared to write becomes unavailable: its old value is history,
not a fallback for later readers. Other parameters remain untouched. This does
not roll back target-system actions.

Undeclared names are declaration errors. Missing/unavailable values block their
consuming actions; actual values must satisfy the destination's existing type
rules. A Flow-dependent Scenario cannot be run independently without its Flow.
Independent Scenarios with no such dependency remain supported.

## Sessions, run values and projections

Each live projection owns its own shared parameter store, mapped sessions and
browser contexts. The same mapped user retains its current session across
Scenario boundaries. Other users and anonymous contexts stay separate.
`session: new` still explicitly replaces only the selected named user's session.
There is no automatic reauthentication, focus repair or context repair after an
error. Retained browser contexts close once when that execution finishes.

Scenario-local unique values remain independent per invocation and live
projection; references to one source reuse its frozen value. Existing relative
time parameters use one UTC base for the complete Flow; fixed `run_time` can
reproduce that base. Shared values and context do not reset or isolate the target.

Contract replays the backend invocation's frozen snapshot, recordings and
execution identity. It neither reads another live projection's created ID nor
uses the final shared store to reinterpret earlier Scenarios. Frontend mock
evidence remains mock evidence. Projection choice remains a host decision.

## Continuation and reports

Inside a Scenario the existing Step policy is unchanged: ordinary assertion
failure continues, explicit leaf stop / ERROR / SKIPPED stops later leaves, and
unavailable data blocks consumers. An include cannot override child policy.

Between Scenarios, the default Flow `stop` requires strict `PASSED` before the
next invocation starts. `continue` attempts later work with still-usable values
and contexts. It does not repair an unavailable session, ignore missing evidence,
guarantee cleanup or erase an earlier failure. The policy is projection-local;
any non-PASSED required chain prevents the overall Flow from passing.

The report retains Flow, Scenario invocation, projection and step/check results.
It distinguishes repeated calls, source pins, mapped users, session generations,
prior failures and blocked reasons. Shared-value provenance records which source
and version was read or written; actual values are sensitive and omitted from
default representations. Arbitrary serialization is not a safe public export.

## Include and review boundaries

A directly scheduled Scenario can contain an ordinary one-level include. Its
child cannot contain another include, include a Flow or publish `write_flow`.
Children can read the containing invocation's Flow snapshot and offer their
existing named results. The scheduled caller chooses the shared write destination.
The existing no-result-re-export rule is unchanged.

Unchanged approved child internals can be reused, but caller ordering, user
mapping, parameter reads/writes and the final obligation still require review.
Measured review savings, environmental independence and resistance to malicious
in-process adapters are not guaranteed by this mechanism. See the
[threat model](docs/threat-model.md) and [task specification](docs/tasks/scenario-flow.md).
