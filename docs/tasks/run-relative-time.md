# Run-relative UTC time parameters

Status: expression, implementation, independent audit and architect acceptance
authorized by the maintainer on 2026-10-24. Submission is not authorized.
Starting main: `50996af`. Keep schema version 1 and one-level pinned inclusion.

Delivery: [local acceptance](run-relative-time-acceptance.md) passed on
2026-10-24. Submission remains subject to separate maintainer authorization.

The maintainer subsequently accepted the completed task and separately
[authorized public submission](run-relative-time-acceptance.md#subsequent-submission-authorization-2026-10-24).
That instruction changes the delivery gate, not the approved expression or scope.

## Purpose and source boundary

Make expiration inputs and recent-time query windows repeatable without editing
fixed dates. Sources are the public declaration contract, run-value implementation
and synthetic Records/Documents examples. No private workspace or product access.
This does not test a scheduler, advance a clock, prove future expiration, or make
an external environment reproducible. It introduces no assertion vocabulary.

## Approved declaration

```yaml
parameters:
  expires_at: {from_run: time, offset: {days: 7}}
  window_start: {from_run: time, offset: {hours: -24}}
  window_end: {from_run: time}
```

Recognize the marker only as the whole value of a directly declared parameter,
alongside the existing `from_run: unique` and `concat` forms. Subsequent uses
remain `from_parameter`. The keys are exactly `from_run` and optional `offset`.
An offset contains exactly one of `days`, `hours`, `minutes`, `seconds` with a
strict integer value (not bool, float, string or null). Positive means future;
negative means past; zero is allowed. Omission means zero; an empty mapping does
not. One day is exactly 24 hours. No month/year/calendar/DST arithmetic, custom
timezone/format, expression, dynamic unit, or direct step-level marker.
Nested marker-looking parameter data remains literal. Unknown keys are rejected.

The resolved value is always a UTC string `YYYY-MM-DDTHH:MM:SS.sssZ` with exactly
three fractional digits. Freeze the clock to milliseconds by truncation once,
before applying offsets. No rounding, locale dependency or implicit conversion.
Offsets exceeding the representable Python datetime range are invalid; an
otherwise valid offset that overflows the selected base fails before any action.

## Runtime and replay

- A selected logical run containing any time marker, even an unused declaration,
  reads the UTC wall clock exactly once. All parameters, included leaves,
  projections and polling attempts use that base. Independent runs read anew;
  they may legitimately obtain the same millisecond.
- Add optional keyword-only `run_time=None` to `run_scenario` and the explicit
  low-level run-value binding entry point. A supplied value must be a real date
  in the exact UTC string format above. It replaces the base without reading the
  clock. Invalid supplied values raise a configuration error before port calls;
  never fall back to actual time. No CLI option is part of this task.
- Loading, validation, expansion, include impact inspection, filtered runs and
  runs without time markers never read the wall clock. Fixed input validation
  may occur before filtering. The polling `now`/monotonic clock is unchanged.
- Freeze a fresh declaration copy. Preserve the existing two-value return of
  `bind_run_values` and the existing unique-token behavior; time metadata may
  travel with the bound declaration. Repeated/concurrent executions must not
  mutate the source declaration or share mutable evidence.
- Record the effective base, whether it came from actual or fixed time, and
  resolved direct time parameters in explicit report metadata. Keep these fields
  keyword-only, repr-hidden and marked sensitive. Do not serialize all parameters
  or composed/business values. Metadata names may use compiled include scopes.
  Default representations and configuration errors must not leak supplied data.
- Contract uses the already frozen declaration and original provider recordings;
  it must never generate a new base. Low-level projections reject unbound time
  markers before ports, just as they reject unbound unique markers.
- Existing concat, parameter overrides, response-dependent include arguments,
  user mappings, named results, request/query/header constraints and atomic
  binding rules are unchanged. Time-derived values are strings, not permission
  to compare dates with numeric `field_compare`.

Fixed time freezes test inputs only. It does not change host/server time, unique
tokens, sessions or persisted data. A real server may correctly reject an old
fixed expiration as already expired. Reproduction claims must state this limit.

## Development and acceptance plan

1. Declaration positives: all units/signs/zero/default; negatives: malformed
   marker, unknown/extra keys, empty/multiple units, bool/float/string/null,
   unsupported format/unit and direct action marker. Preserve literal data.
2. Runtime: one clock read, canonical milliseconds, fixed replay without a clock
   read, malformed/nonexistent dates, overflow, no side effects on binding error,
   independent and concurrent runs, concat and report sensitivity.
3. Integration: all four projections, real browser mock/live input and outgoing
   evidence, polling reuse, low-level unbound rejection, included parameters and
   overrides/named results, symbolic expand and impact, unchanged declaration.
4. Real synthetic consumers: Records creation/readback with expiration and an
   independent Documents recent-window query. Tests use known inside/outside and
   boundary data to check inclusion/exclusion with existing checks. They must
   not manufacture responses from assertions. Keep a false-filter counterexample.
   Public sample basic response checks alone do not claim correct time filtering.
5. Update the public contract, onboarding, roadmap, English examples and executable
   documentation guards. Preserve historical task/measurement records; append
   current delivery status where appropriate. No frozen mutation-result changes.
6. Independent audit, full suite with Chromium, fresh dev-only core suites,
   import litmus, lock, hygiene, diff/index checks and final architect acceptance.
   Assertion vocabulary, ports, dependency lock, CI, MANIFESTO and BRAND stay
   unchanged unless a demonstrated necessity is separately explained.

All changes remain unstaged and uncommitted. Do not push, create a branch or PR,
access the private workspace, expand nesting, implement Flow, general generators,
time ordering assertions, environment management or unrelated cleanup.
