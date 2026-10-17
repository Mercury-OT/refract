# Browser adapter support

`refracto_browser.BrowserSupport` supplies Playwright browser lifetime, one
authorized primitive, request and response recording, bounded completion waits,
and cleanup. It is optional support for a product adapter implementing the
existing `StepwiseUiDriver` port. The core still owns action order, wait actions,
assertions, and continuation/stopping decisions. Ordinary assertion failure now
continues by default; a leaf `on_failure: stop` stops after that failure. Execution
or evidence-integrity errors still stop. The helper does not retry an action or
repair its evidence. See [the execution contract](../SCENARIO.md#continuing-and-stopping).

Install it with the browser extra and Chromium:

```bash
pip install -e ".[browser]"
playwright install chromium
```

The `demo` extra continues to include Playwright. Installing only the core or
`dev` extra does not install it; core imports and offline tests need no browser.

## Connect an adapter

The adapter supplies logical target mappings, authentication options, a read-only
rendering callback, and any logical request-path mapping. Neither selectors nor
input values come from expected assertions. This small example maps one page,
one button, and one input:

```python
from refracto import ports
from refracto_browser import BrowserSupport


def read_rendered(page):
    rows = page.locator("[data-record-id]")
    identified = []
    for index in range(rows.count()):
        row = rows.nth(index)
        identified.append({
            "id": row.get_attribute("data-record-id"),
            "fields": {"name": row.get_attribute("data-record-name")},
        })
    return {"records.rows": {"identified": identified, "anonymous": []}}


class RecordsUi(ports.UiDriver, ports.StepwiseUiDriver):
    def __init__(self, base_url):
        self.base_url = base_url
        self.browser = BrowserSupport(
            base_url, read_rendered, timeout_ms=5000,
            logical_path=lambda actual_path: actual_path.removeprefix("/"),
        )
        self.elements = {"records.save": "#save", "records.name": "#name"}

    def supports_stepwise_mode(self, mode):
        return mode in {"live", "mock"}

    def open_stepwise(self, scenario, session, *, mode, mock_plan=None,
                      mock_queue=None, user=None, session_generation=0,
                      context_id=""):
        # This adapter defines session as Playwright browser context options,
        # for example an authenticated storage_state supplied by its caller.
        return self.browser.open(
            mode, mock_plan=mock_plan, context_options=session,
            mock_queue=mock_queue, user=user,
            session_generation=session_generation, context_id=context_id,
        )

    def perform_step(self, scenario, step, context, permit):
        if permit.action == "open":
            if permit.target != "records.page":
                raise ValueError("unknown page target")
            return self.browser.perform(context, permit, url=self.base_url + "/")
        selector = self.elements.get(permit.target)
        if selector is None:
            raise ValueError("unknown element target")
        return self.browser.perform(context, permit, selector=selector)

    def snapshot(self, context):
        return self.browser.snapshot(context)

    def close_stepwise(self, context):
        self.browser.close(context)
```

`open` creates an owned browser context at `about:blank`; the authorized `open`
primitive performs navigation. It does not log in or prepare business objects.
An `open` permit takes one absolute same-origin URL and no selector. A `click` or
`fill` takes one CSS selector and no URL. Only `fill` accepts a value, which must
already be a string. The helper passively waits for visibility and then requires
exactly one visible match. It never chooses an arbitrary match or adds an extra
business action to make an assertion pass.

Core-issued permits are single-use and bind the logical user, current session
generation, and context ID as well as the run/action IDs. The adapter forwards
the context binding when opening it. A permit from a different user, an old
session, or another context is rejected before acting. Treat returned contexts as opaque.
Use each helper and its contexts on the thread that created them. Concurrent
contexts on that thread own separate browsers and share only the Playwright
runtime; closing one leaves the others usable. `close` is safe to repeat.

Core retains one context per current user/session, reuses it when switching back,
and replaces only the selected user's context after `session: new`. It closes
all remaining contexts on exit. The authentication adapter supplies fresh storage
for the same account; it does not restore permissions or replay a hidden login
workflow. Anonymous execution opens a fresh context without authentication data.
A Scenario may explicitly declare `anonymous` alongside named users. Core uses
runtime `user=None` and generation 0 for its anonymous context, keeps it separate
from every named user's context, and may reuse it only within the same projection.
Returning to a named user reuses that user's retained session, not the anonymous
context. Anonymous participation cannot request `session: new`; the loader also
rejects a renewed child alias mapped to anonymous. Multi-user child mappings are
resolved per leaf before the same context and permit checks, with no new loop.
For a core-bound anonymous context the helper rejects storage state, HTTP
credentials, client certificates, and Authorization/Cookie/Proxy-Authorization
headers rather than inheriting them. This is a bounded configuration check, not
a guarantee about every custom authentication mechanism in arbitrary adapters.
These checks enforce the declared adapter protocol, not a malicious adapter's
truthfulness or independent proof of server-side identity.

The executable [Demo adapter](../adapters/demo/ui.py) uses the same helper with
its own mappings and rendering interpretation. Response normalization remains
the product adapter's responsibility.

The helper extracts query keys and values from each actual request URL before
logical-path mapping, routing, and recording. `logical_path` receives only the
path. `RequestSpec.query` preserves decoded wire strings, including empty values;
expected query values never supply actual evidence. Percent escapes and
plus-space encoding are decoded once. Malformed escapes, invalid UTF-8, and
duplicate decoded keys stop execution rather than being silently forwarded as
a supported request.

For UI `expect.request`, omitted `query` keeps the existing method/path/body
scope; `query: {}` requires no parameters; a nonempty query requires exact
decoded equality, including no extra keys. Numeric `1` and string `"1"` have
the same wire spelling, while JSON body and response comparisons remain
type-strict. If one method/path-associated request exists, a wrong query fails
the request check. With several candidates, an explicit query may select exactly
one exact match; zero or multiple matches remain ambiguous errors. Unassigned
or background traffic cannot satisfy an assertion, even with a matching query.
See [the query contract](../SCENARIO.md#request-query-parameters).

## Request origins and completion

Same-origin `fetch` and asynchronous `XMLHttpRequest` started in the targeted
DOM event handler carry that action's origin. Supported handlers include
`addEventListener`, `onclick`/`oninput` properties, and inline click/input
handlers. Explicit Promise callbacks registered while a supported handler or
callback is running inherit its origin:

```javascript
button.addEventListener('click', () =>
  Promise.resolve().then(() => fetch('/records'))
);
```

Native `async`/`await` continuations and timer callbacks do not inherit origin.
For example, a fetch before the first `await` may belong to the action, while a
fetch after that `await` remains diagnostic. Navigation-driven fetches are also
diagnostic. Matching a declared method/path, returning an expected response, or
arriving during another action never creates an origin. Each recorded supported
request has its own request ID, paired response, and trace identifier.

The helper waits for the current action's tracked requests and event-handler
completion promises, then offers bounded animation-frame rendering opportunities.
A returned handler promise is only a completion barrier: waiting for it does
not assign an origin to its native async continuations. Collection includes the
complete response body. Background traffic does not impose a global network-idle
condition. Diagnostic records collected between actions are delivered with the
next action's evidence.

`timeout_ms` defaults to 5000 and must be positive and finite. Target readiness,
interaction, request collection, and rendering opportunities share the action's
deadline. A missing declared request still fails through the existing core
rules. Timeouts, transport failures, ambiguous targets, rendering failures, and
cleanup failures are visible errors; browser-operation failures release the
owned resources. Rendering and logical-path callbacks should be short, read-only
functions; Python callbacks must return control to the helper.

## Explicit mock plans

Live mode records actual traffic. Mock mode consumes a caller-authored, ordered
list of `MockResponse` fixtures, including diagnostic background requests:

```python
plan = [
    ports.MockResponse(
        fixture_id="first-list", source="adapter fixture",
        method="GET", path="records", response={"records": []},
    ),
    ports.MockResponse(
        fixture_id="second-list", source="adapter fixture",
        method="GET", path="records", response={"records": [{"id": "r1"}]},
    ),
]
context = browser.open("mock", mock_plan=plan)
```

Repeated endpoints can consume different fixtures. Missing, wrong-order, or
mismatched fixtures abort the request without reaching a live API. Omitting the
plan in mock mode means an empty plan, so any API request fails. Live mode rejects
a supplied mock plan. Evidence preserves fixture IDs and consumption records;
expected assertions never supply mock data.
Set a fixture's optional `query` to a mapping of decoded wire strings to require
an exact query match. `query={}` requires no parameters; the default `None`
retains method/path-only fixture matching. A wrong-query fixture aborts the
actual request without reaching a live API. Query evidence remains in the
traffic/response pair and is checked against the Recorder and fixture plan.

For a multi-context run, core supplies the same `MockResponseQueue` to each
`open_stepwise` call. Forward it as `mock_queue`; do not create a new queue when
switching users or replacing a session. Consumption order is global to that
projection. Core retains an independent fixture plan to verify the observed
consumption and responses. A standalone helper caller can also explicitly share
a queue; unrelated runs must use separate queues.

## Transport and data boundaries

This helper supports finite HTTP responses and JSON-object request bodies. It
rejects cross-origin requests, redirects, synchronous XHR, frame traffic,
workers, and streaming transports when encountered. Service workers are blocked.
Outside fetch/XHR, only GET and HEAD requests for documents, stylesheets, scripts,
images, fonts, media, text tracks, and manifests may reach the server. Other
transports, including `sendBeacon`/ping and form writes, fail before forwarding in
both modes; an empty mock plan never permits an unsupported write to fall through.
Redirects are not followed, so credentials cannot be forwarded to an unvalidated
destination. It is intended for one top-level page; browser-native application
flows beyond these bounds need a separately scoped adapter design.

Internal request-association headers are removed before traffic reaches the
server. At request start the helper generates a fresh local trace, which replaces
any application-supplied `traceparent` when the request is forwarded. Exactly one
trace header reaches the server and its value matches the recorded evidence.
Request identifiers use random bytes available on ordinary HTTP origins as well
as secure origins. The forwarded `traceparent` supplies local test correlation, including
the Demo's backend-state trace; it is not proof of independent provenance.
Instrumentation runs inside the tested browser and does not protect against a
malicious application, adapter, or normalizer.

Helper/context repr and helper error messages omit bodies, queries, browser handles,
context options, bound values, selectors, and URLs. Raw port objects still hold
sensitive request/response data and are not a safe logging or export format.
The rendering callback must interpret existing UI state without clicking,
navigating, or sending requests. The helper never sends a replacement API action
to repair missing browser evidence.
