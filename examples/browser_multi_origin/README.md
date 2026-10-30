# Bounded multi-origin records consumer

This synthetic application uses three real local HTTP listeners: a page, an API,
and static scripts. It does not modify an external product or use private source
material. `adapter.py` supplies only target/rendering mappings, response
normalization and existing authentication wiring. Browser collection remains in
`refracto_browser`.

The same ten files under `scenarios/` run against two separately written frontends:

- `promise.js` starts requests inside a click handler or registered Promise work.
- `async.js` starts each request after a native `await`. Its missing action
  association is an explicitly retained limitation, not a passing substitute.

Every run starts fresh local application state. Record IDs are actual observed
strings entered into the application's ID input; no dynamic target syntax is
needed. A named session places an account value in the page's local storage.
The application itself sends Authorization only to its API. Anonymous contexts
have no account value. The server chooses the response and CORS headers without
reading the Scenario or adapter expectations.

## Fixed panel

| Case | Obligation |
| --- | --- |
| c01 | Page and independently hosted script are visibly ready. |
| c02 | Public list contains the three initial records. |
| c03 | Category query reaches the API unchanged and filters records. |
| c04 | Page two uses the declared limit and differs from page one. |
| c05 | Fill and create a record with a generated unique code. |
| c06 | Read the newly created record by its actual ID. |
| c07 | Change a created record and read back the changed content. |
| c08 | Delete a created record and observe absence from the API list. |
| c09 | An anonymous protected write is refused. |
| c10 | A named user can perform a protected read. |

All 20 implementation/case units remain in measurement results, including
missing-association failures. The maintenance variant changes the control IDs
and API path prefix through two explicit adapter configuration fields. It must
not change any Scenario file or business obligation.

## Run and inspect

With the browser dependencies and Chromium installed, from the repository root:

```sh
uv run --frozen pytest -o addopts='' -q tests/browser/test_multi_origin_consumer.py
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label candidate --output /tmp/browser-candidate.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label maintenance --maintenance --output /tmp/browser-maintenance.json
```

The measurement command exits zero when the complete panel is recorded. **It is
not a business acceptance command**: each row retains its real status, and a
business acceptance gate still requires `status == PASSED`. The reports include
synthetic request bodies and credentials and must not be treated as a general
safe-to-publish export format.

To reproduce the old helper comparison, extract commit `3a0b1a5` into a temporary
directory and put that source before the current repository on `PYTHONPATH`.
Execute the current `run.py` with `--legacy` and `--expected-engine` pointing to
the extracted baseline. It verifies both core and browser module imports before
running the identical application and declarations. The old helper's rejection
is a measured outcome, not a hand-written baseline estimate.

After producing all three panel reports:

```sh
uv run --frozen python -m examples.browser_multi_origin.measure --baseline /tmp/browser-baseline.json --candidate /tmp/browser-candidate.json --maintenance /tmp/browser-maintenance.json --output /tmp/browser-cost.json
```

The recomputation rejects missing/duplicate units and changed Scenario hashes.
Additional complete candidate runs can be supplied with repeated `--repeat`
arguments; they are reported separately rather than merged into the 20-unit
capability denominator. These small runs describe observed stability only.
It counts Python lines touched by non-comment tokens (including docstrings and
embedded data), JavaScript nonblank lines, YAML nonblank lines and mapping entries
separately. Product adapter, reusable browser collector, target and test/harness
code are not mixed. Runtime is measured; human writing, diagnosis and review
time are explicitly unmeasured. There is no LOC threshold, generalized adoption
claim or claim that this single maintenance change predicts future effort.
