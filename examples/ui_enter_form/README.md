# Submit an ordinary form with Enter

This neutral application searches the same two built-in records as the existing
[Enter search example](../ui_enter_search/README.md). Its input belongs to a real
HTML form with native validation and a normal submit button. Pressing Enter lets
the browser submit that form; the application's own handler cancels navigation,
sends a GET request, and renders the response in place.

`listener.js` attaches a submit listener and uses a Promise chain. `property.js`
uses an onsubmit property handler, cancels navigation synchronously, then awaits
before its fetch. Both reuse one service and dataset, so these are two handler
variants, not independent products or evidence of adoption savings.

The [Scenario](../ui_enter_search/scenario.yaml) and
[adapter](../ui_enter_search/adapter.py) are reused unchanged: open, fill, Enter,
then check the actual query, response, and rendered records. There is no new
submit action, YAML field, adapter preparation, focus repair, hidden button click,
replacement API request, or target modification by the adapter.

With the browser dependency and Chromium installed:

```sh
uv run --extra browser python -m examples.ui_enter_form.run
uv run --extra dev --extra browser pytest tests/browser/test_enter_form_consumers.py
```

The CLI runs live e2e only, using both variants by default; choose
`--implementation listener` or `--implementation property` for one. It exits zero
only when all selected runs pass. The JSON records the original Scenario hash,
new and shared target-source hashes, observed server/browser requests, response
and rendered results, key receipts, user/session/context counts, and cleanup.
It does not print the synthetic credential. An API action port counts and rejects
sends, so a direct API call cannot repair a failed browser operation.

Normal target [sources](target-sources.json) were authored and frozen before the
consumer wrapper and tests. They remain unchanged; separate test subclasses
introduce ignored submission, wrong queries/responses, stale rendering, native
validation rejection, programmatic/wrong-form submission, and focus theft.
Each run checks source hashes before and after execution. The shared service and
original keyboard-example sources retain their existing hash checks as well.

Source pinning identifies the checked bytes; it does not prove human approval,
independent evidence, or correctness of arbitrary adapter code. Browser evidence
uses the existing bounded association and trust model. Correct status alone does
not establish the expected records or UI result, and the UI checks only cover the
expected name and one known excluded name.

This example requires a unique, already focused text/search input with a supported
native default submitter. The product must cancel native navigation itself.
Programmatic requestSubmit, another form's traffic, and same-path background work
cannot replace the expected submission. A missing associated request is ERROR;
actual wrong query/response/rendered values are FAILED. Native navigation,
redirects, frames, downloads, file uploads, other keys and automatic focus repair
remain outside this task. See the [task contract](../../docs/tasks/enter-form-submission.md).
