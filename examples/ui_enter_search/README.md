# Search with an explicit Enter

This new neutral application searches two built-in public sample records by name
substring. It starts with **Quarterly report** and **Invoice** visible. Its ordinary
search input sends a real HTTP GET and renders the returned records in place.
The static dataset is an application fixture, not hidden adapter preparation.

Both handler forms run the exact same [Scenario](scenario.yaml): open the page,
fill `report`, then press Enter in that already focused input. `listener.js` uses
a keydown listener and a Promise chain; `property.js` uses an onkeyup property
handler with native await before the fetch. They share one new server and dataset,
so these are two bounded mechanism checks, not independent products.

With the optional browser dependency and Chromium already installed:

```sh
uv run --extra browser python -m examples.ui_enter_search.run
uv run --extra dev --extra browser pytest tests/browser/test_enter_search_consumers.py
```

The CLI runs only live e2e and exits successfully only when both runs pass. Use
`--implementation listener` or `--implementation property` for a single run. Its
JSON records the Scenario/source hashes, actual server requests and responses,
action-associated browser traffic, key-delivery receipts, rendered result names,
session/context counts, and cleanup. It omits credential material.

The fill check reads the DOM input's actual value and stops on ordinary failure.
The press checks the actual query, response status, one-member response list and
expected response name. UI checks require one expected-name row and zero rows
with the known nonmatching name. They do not establish the absence of every
possible unexpected row or cover pagination. A checked key receipt accompanies
the request and UI observations; it does not independently attest a hostile
adapter's behavior.

Normal [application sources](target-sources.json), including the HTML-producing
server, were frozen before adapter and consumer test authoring. Every run verifies
their hashes before and after execution. The minimal adapter receives action
inputs and execution identity, never assertions. It maps logical targets and
reads existing DOM fields; it does not prepare records, alter the page, add object
identity, focus the input for a press, click a control, or repair a search. An
explicit `reader` session supplies a synthetic demonstration credential through
normal browser storage. Native `BrowserNetworkPolicy` limits API and credential
traffic to the local service. The API action port rejects all sends, and the
consumer records that it was never called.

Separate target subclasses in the browser tests intentionally ignore Enter,
send the wrong query, keep stale rows, render the wrong rows, or steal focus after
fill. Ignored Enter produces a step ERROR because no associated request exists;
wrong queries and observed wrong results produce step FAILED. Focus theft produces
a step ERROR before key dispatch. Runs aggregate both failure kinds as FAILED.
Its document-level Enter witness makes an extra HTTP request
if a key is erroneously sent; the control verifies that no such request occurred.
Each run creates and closes one browser context with one session; no fault is
repaired or silently replaced by an API call.

This example covers an ordinary main-document search input and bounded in-place
HTTP work. Native activation, form submission, navigation, frames, other keys,
IME and contenteditable are outside this slice. The adapter opts into live mode
only; no mock run is presented as live evidence. Background timing or URL matches
are not used as causal evidence. See the [Enter specification](../../docs/tasks/ui-enter-press.md).
