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

## Hover with page-only evidence

`do: hover` moves the pointer once onto a literal logical `target`; the existing
`expect.ui` checks describe the required page result. An adapter opts in through
`supports_hover(mode)`, returning exact True only for supported modes. The base
driver returns false; unsupported hover is rejected before context creation.
Map the target to one native CSS selector and pass the unchanged permit to
`BrowserSupport.perform(context, permit, selector=...)`.

The helper pins one visible main-document element and uses its in-viewport
center point. A descendant hit is allowed. It requires actual trusted pointer
movement, the same connected element and a valid hit test through the final
snapshot. Missing, duplicate, hidden, covered, replaced or unavailable targets
produce an evidence error. It does not scroll, force an interaction, click,
focus, alter styles or move away and back to manufacture another mouseenter.
An already-positioned pointer can yield a movement receipt; that is not proof
that another enter event occurred. Existing page checks determine the result.

Completed evidence carries `UiHover(target_matches=1, pointer_on_target=True)`
in `UiActionEvidence.hover`. Core requires strict types, checks execution
identity, and copies it into `StepResult.hover`. Other actions must not claim
this receipt, and a skipped action cannot replace it. An observed wrong page
result is FAILED; missing delivery or observation evidence is ERROR. These are
bounded consistency checks, not protection against hostile adapter/page code.

Hover-related requests stay background diagnostics and cannot satisfy a hover
or a later click. This slice rejects request, response and backend_state sections
on hover, including empty sections; declare a subsequent click as its own step
when that action makes a request. Mock execution still requires explicit mock
responses and cannot fall through to live services. Navigation, new documents,
additional tabs/frames and downloads during hover or its protected idle gap are
unsupported. The next authorized action retains its existing rules after that
gap has been checked.

Once a mock context accepts hover or Escape, all unassociated API requests in that context
are aborted and noted diagnostically, including later arrivals. They cannot
consume the ordered fixtures reserved for associated actions. This is a
conservative restriction for late background work, not a claim to identify its
origin. It can affect pages whose menus depend on such background responses;
those pages need live evidence or a separately reviewed extension. Contexts
without either action retain their existing mock behavior; live background traffic is
unchanged. An aborted request does not acquire an invented response record.

Backend does not perform hover: it reports the UI-only step NOT_APPLICABLE and
the UI obligations not checked. A hover-only backend selection is EMPTY, not
PASSED. A mixed Scenario can pass its backend request checks without proving
menu behavior; use frontend or e2e for that evidence. Contract likewise cannot
prove pointer delivery. No aggregation or projection-selection rule changes.
See the [menu consumer](../examples/ui_hover_menu/README.md) and
[bounded task](tasks/ui-hover.md). The consumer checks that the menu item starts
hidden before testing its reveal; missing menu structure is not an empty list.

## Escape on an already focused input

`do: press`, literal `target`, and `key: Escape` deliver one actual down/up pair
to a unique visible enabled editable text/search input in the main document.
The driver must explicitly support supports_key_press(mode, "Escape"). The
existing UiKeyPress receipt carries Escape, strict integer counts of 1 and
focused exactly true. Enter-only capability is insufficient.

The target must already have focus and remain the same mounted, focused object
through collection. Transient focus loss is an error even if restored. Do not
call focus, click, locator.press, dispatchEvent or hide a panel to implement this
primitive. Escape does not require a keypress event and cannot borrow Enter's
implicit click/form-submission chain. Only UI expectations are supported.

The [consumer](../examples/ui_escape_suggestions/README.md) checks actual input
content and associated suggestion-panel visibility before and after Escape.
Unavailable or ambiguous structure cannot become false visibility. A valid
delivery with wrong page results is FAILED; unavailable delivery/observation is
ERROR. This does not cover dialogs that remove the input or move focus.

Escape handlers and their asynchronous work receive no request-evidence origin.
Their traffic stays diagnostic and cannot rescue a later declared request. After
the first Escape or hover in a mock context, unassociated API traffic is aborted
diagnostically for the rest of that context, without consuming ordered fixtures
or reaching live services. Live diagnostics keep existing network policy; this
does not claim arbitrary background-response-dependent pages work under mocks.
This quarantine is BrowserSupport policy. Core still validates custom-driver
receipts, associated traffic and existing mock identities; it does not impose
this helper's scheduler on separately supplied diagnostic mock fixtures. Such
diagnostics are not Escape request evidence or proof of live application behavior.
Navigation, document replacement, new tabs, frames and downloads remain guarded
during Escape and its protected idle gap. The next authorized action resumes its
own documented rules. No automatic repair or rollback of product effects.
Rejecting a paused secondary target closes the owned browser context, without
resuming that target. Closing only the new tab could leave the original key
dispatch pending. The ordinary failure path still releases the browser and
Playwright resources; no other browser context is selected from target metadata.

Backend skips requestless Escape and records unchecked page obligations; pure
UI selections are EMPTY for backend/contract, not PASSED. The existing combined
report rules and one-level Scenario/Flow composition remain unchanged. See the
[specification](tasks/ui-escape-press.md) for scope and verification requirements.

## Enter on an already focused input

`do: press`, `target`, `key: Enter` performs one real key down/up pair, without
focusing or clicking the target. An adapter opts in with
`supports_key_press(mode, key)`, returning exact True only for modes/keys it
implements; the base driver returns false. Existing drivers retain their
ordinary actions but reject a press Scenario before opening a context.

Map the logical target to one native CSS selector and pass the original permit
to `BrowserSupport.perform(context, permit, selector=...)`. Do not call focus,
locator.press, dispatchEvent or a direct API to implement the primitive. The
helper permits a unique visible, enabled, editable text/search input in the main
document. It pins the element, requires it already be active, and rechecks at
trusted key dispatch. Hidden duplicates do not count as visible targets. A focus
change during the active press invalidates it even if focus returns. Collection
does not repair state, and errors cannot roll back effects already produced.

Completed evidence has `UiKeyPress(key, target_matches, focused, keydown_count,
keyup_count)` in `UiActionEvidence.key_press`. The key is Enter, all three counts
are strict integer 1, and focused is exactly True. Core validates identity and
copies the receipt into `StepResult.key_press`, including when a subsequent
request/check fails. Other actions must omit this receipt. Custom adapters must
observe the facts rather than echo a permit. This is local consistency under the
[threat model](threat-model.md), not attestation against hostile adapter/page code.

Keyboard listener/property callbacks reuse bounded request-origin capture.
Synthetic nested events and background/timer traffic cannot borrow a trusted
Enter callback's origin. Native-await evidence retains the native transport's
existing bounded ancestry rules; it is not a general asynchronous-work promise.
Missing or ambiguous associated request evidence produces ERROR; a reliably
associated wrong query or response produces ordinary FAILED. A mock must be an
explicit fixture; no missing fixture is replaced by a live request.

The helper excludes modifiers, repeated/other keys, sequences, IME,
textarea/contenteditable, frames, native form-navigation requests, document
navigation and downloads. The scoped-click navigation feature does not extend
to Enter. See the [frozen synthetic search consumer](../examples/ui_enter_search/README.md)
and [task contract](tasks/ui-enter-press.md). Its UI checks cover known rows, not
all possible filtering, pagination or accessibility behavior.

### Same-page form submission after Enter

The unchanged press expression also supports the browser's default Enter
activation of the input's owning form. The helper pins the actual form and its
first native submitter (button type=submit or input type=submit, including an
external form-associated control). It checks the real key, native click and
submit chain against those objects. Native submission without a default submitter,
or through an image submitter, is unsupported; the helper never selects a fallback or calls submit,
requestSubmit or click to complete the action.

The product's submit handler must cancel navigation, including through normal
onsubmit return-false behavior. Its fetch/XHR may then supply associated traffic
using the existing bounded synchronous, Promise and native-await paths. The
implicit click is transition evidence only; requests from its click handlers
remain diagnostic. Programmatic submissions, including requestSubmit called
inside a real key/click/submit callback, cannot borrow submit origin. A trusted
event flag alone is not sufficient proof.

Normal validation or cancellation can leave a valid Enter receipt but no submit
request. If a request was declared, existing missing-evidence handling produces
ERROR. The helper does not bypass validation or supply cancellation on behalf of
the application. Disabling the submit button after the verified submit need not
invalidate its history; the existing input identity/focus checks remain strict.
Native navigation, unsupported transitions and background traffic keep their
existing boundaries. See the [specification](tasks/enter-form-submission.md) and
[new form consumer](../examples/ui_enter_form/README.md), which reuses the old
Scenario and adapter without changing their bytes.

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

    def open_stepwise(self, session, *, mode, mock_plan=None,
                      mock_queue=None, user=None, session_generation=0,
                      context_id=""):
        # This adapter defines session as Playwright browser context options,
        # for example an authenticated storage_state supplied by its caller.
        return self.browser.open(
            mode, mock_plan=mock_plan, context_options=session,
            mock_queue=mock_queue, user=user,
            session_generation=session_generation, context_id=context_id,
        )

    def perform_step(self, context, permit, *, business_header_names=()):
        self.browser.validate_request_header_names(context, business_header_names)
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
An `open` permit takes one absolute same-origin URL and no selector. An ordinary
`click` or `fill` takes one CSS selector and no URL. Object-specific clicks use
the separate mapping below. Only `fill` accepts a value, which must
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

## Object-specific clicks

For a click with `object_id`, opt in through
`supports_object_targeting(mode)` on the StepwiseUiDriver. The default is false;
only exact True declares support. Core rejects unsupported scoped Scenarios
before opening a context or performing a business action in that projection.
The existing perform_step signature does not change.

Map the logical control to an `ObjectTarget`, not a selector interpolated from
the requested ID:

```python
from refracto_browser import ObjectTarget

edit_target = ObjectTarget(
    rows=".record",
    control="button.edit",
    read_id="row => row.querySelector('a.details').getAttribute('href').split('/').at(-1)",
)
# In perform_step, after checking the logical target:
evidence = browser.perform(context, permit, object_target=edit_target)
```

This illustrative reader extracts a string ID from the target's ordinary detail
link; it is appropriate only for a product whose link contract has that form.
The executable [two-consumer example](../examples/ui_object_targets/README.md)
has tested mappings for ordinary detail links and form actions. Identity parsing
belongs to that reviewed product mapping, not to a universal URL heuristic.

The frozen mapping contains native CSS row/relative-control selectors and a
read-only JavaScript reader. The reader receives one actual row, not the requested
ID or expectations. It must observe the product, not create identity metadata or
guess from names/order. This is adapter code, not a Scenario expression language
or a sandbox. Missing or malformed visible-row identities are errors, not ignored
rows. Numeric identities outside JavaScript's safe integer range are rejected;
use an actually observed string identity where the product supplies one.

The helper requires one matching visible object and one visible control, waits
only within the existing action deadline for missing readiness, and rejects
ambiguity. It pins the selected elements and checks identity and uniqueness again
before application click handlers. Replaced elements, changed identities or new
duplicates cannot redirect a click silently. No synthetic/forced click, extra
navigation, pagination, API fallback or DOM identity injection is performed.
The guard cannot undo earlier pointer/hover effects and is not an atomic
transaction against hostile page code. Legitimate row removal by the accepted
click handler is allowed.

The in-page consumers above remain unchanged. A separate
[navigation consumer](../examples/ui_object_navigation/README.md) exercises
object-scoped clicks that open a new HTML document in the same tab and exact
origin (scheme, host and port). Supported forms are the pinned anchor's default
navigation and synchronous navigation from the accepted click handler. For an
anchor, map the control to the anchor itself, not an enclosing row or inner span;
clicking a descendant of the pinned anchor remains valid.

The helper retains the old document's actual selection receipt on the host,
bound to its action, context and source document. It checks the native navigation
observation against one main-frame document request and committed loader. It
does not match navigation by URL, timing or expected content. Lost or ambiguous
proof is an error. Existing current-document completion remains supported.

This bounded navigation requires a successful same-origin GET HTML document.
Redirects, other tabs/frames, native form submission, downloads, deferred
Promise/await/timer navigation and unfinished old-document action work are not
supported. They cannot be treated as an equivalent successful click. Context
cleanup does not undo a target-side effect that already occurred.

New-document startup requests remain background/diagnostic traffic, including
when their URL matches an expectation. Navigation HTML is not an API response.
Use existing UI checks to inspect the destination, then subsequent explicit
steps for further actions or API reads. A correct selected-row receipt does not
prove that the product opened the right editor; the example checks the editor's
actually rendered object identity before filling or saving. No YAML field or
core port changes are needed; see the
[bounded contract](tasks/same-tab-object-navigation.md).

`UiActionEvidence.object_selection` holds a `UiObjectSelection` with the actual
object_id and exact integer object_matches/control_matches, both 1. Core checks
it against the signed permit and retains an owned copy on StepResult. It is
required even without a request; unscoped actions must not return it. IDs and
receipts are hidden from default repr, but generic serialization is not safe.
This receipt provides local consistency, not independent proof that an arbitrary
adapter is truthful. Actual request association and request/response checks still
apply, including when the target sends a request for the wrong object.

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

Optional `expect.request.headers` entries constrain the actual associated
request by case-insensitive name and exact string value. Other browser headers
are allowed, and omitted or empty mappings add no header constraint. The helper
reads the complete browser-observed request header block, including cookies, then records the
effective trace replacement and removal of internal association markers. It
does not insert declared values into the page's request. `RequestSpec.headers`
remains a business-input mapping; the browser's authoritative observations are
`RecordedResponse.request_header_items`, not credential-bearing business inputs.
This is the browser interception boundary, not packet capture: `route.fetch`
can add transport-owned headers such as `Host` and `Content-Length` when it
forwards the request. Those transport names cannot be business declarations.
Actual-server tests compare the business and credential values, effective trace,
and removal of private markers independently.

Before performing a primitive, call
`validate_request_header_names(context, business_header_names)` as in the adapter
above. Core supplies a sorted tuple of unique lowercase names, without expected
values or the rest of the request expectation. This mechanical name check rejects declared business
headers that collide with the context's `extra_http_headers`, which the adapter
supplied as session credentials. It does not use expected values to drive the
page. Standard credential and transport header names are also forbidden as
business declarations. Product-specific authentication mechanisms beyond these
context headers remain the adapter's responsibility.

UI adapters receive neither Scenario nor Step. The permit carries the current
action input and execution identity, not the complete resolved-binding map.
Core retains expectations, evaluates actual evidence, and keeps diagnostic
bindings in its report. Do not reconstruct the old interface through a wrapper
or read expectations to select targets or fill observations. This input boundary
reduces accidental coupling; it does not sandbox in-process adapter code. See
the [threat model](threat-model.md).

When one associated method/path request exists, a wrong or missing declared
header produces a failed request assertion. With several candidates, an explicit
query narrows the set first and declared headers can then select exactly one.
Zero or multiple matches are errors. Unavailable header evidence cannot be
silently discarded during selection, and headers never promote background or
replayed traffic into the current action.

Response `header_equals` and `header_absent` checks use the complete ordered
`RecordedResponse.header_items` pairs before normalization. Names are
case-insensitive; values are exact strings, with no splitting or semantic
interpretation. An empty value is present. `None` means unavailable evidence,
not absence; only an explicitly complete block can prove absence. Repeated
entries are retained. A repeated asserted name is unsupported evidence and an
error, while unrelated repeated entries such as `Set-Cookie` remain valid.
These raw fields are sensitive and hidden from default representations.

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

The legacy single-origin helper leaves native `async`/`await` continuations
diagnostic. The opt-in multi-origin Chromium collector additionally associates
requests after native `await` using bounded browser async stacks and exact
callback invocation markers. It accepts only supported `await`/`Promise.then`
transitions to the nearest marker. A null-origin callback is a barrier, including
a synthetic event invoked inside a trusted action. Missing or truncated ancestry,
timer callbacks and unknown async transitions cannot inherit an older action.
No source-function, endpoint, response-content or time-window matching is used.
Async collection is capped at 32 parent stacks; parsing also bounds frame counts
and names. Deeper or unavailable relationships remain unsupported evidence, not
permission to infer an origin from a matching request.

A helper directly invoked by an action may retain that action's origin even if
the application does not await it. This proves invocation ownership, not that
the action waited for completion. Late observations retain their original
identity and cannot satisfy the next step. Independently scheduled background
work, including other consumers of a shared promise, remains diagnostic.
Navigation-driven fetches also remain diagnostic. Each supported request keeps
its actual network identity and paired response; a browser identity does not
invent a server trace. See the [native-await task](tasks/browser-native-await.md)
for the feasibility gate and negative controls.

The helper waits for the current action's tracked requests and event-handler
completion promises, then offers bounded animation-frame rendering opportunities.
A returned handler promise is only a completion barrier: waiting for it does
not assign an origin to its native async continuations. Collection includes the
complete response body. Background traffic does not impose a global network-idle
condition. Diagnostic records collected between actions are delivered with the
next action's evidence.

For a native post-await fetch, the collector first verifies its invocation, then
claims that exact local fetch handle for passive response-copy reading before
allowing delivery. The application's response remains untouched. Background
handles retire on fetch settlement/rejection without a collector call or body
draining; at most 128 unresolved handles are kept.
An unavailable handle for an associated request is an error. This keeps response
collection working when the application does not read the body itself.

`timeout_ms` defaults to 5000 and must be positive and finite. Target readiness,
interaction, request collection, and rendering opportunities share the action's
deadline. A missing declared request still fails through the existing core
rules. Timeouts, transport failures, ambiguous targets, rendering failures, and
cleanup failures are visible errors; browser-operation failures release the
owned resources. Rendering and logical-path callbacks should be short, read-only
functions; Python callbacks must return control to the helper.
The action deadline does not forcibly preempt a blocked renderer or synchronous
protocol call. It is not an operating-system process execution limit.

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
Optional `request_headers` fixture entries constrain only their named request
headers. Optional `response_headers` supply independent response header values
alongside the default JSON content type. Both mappings are authored independently
of Scenario expectations. A wrong request-header fixture aborts without consuming
it or contacting the API. Response evidence is collected from Chromium after
fulfilment, including generated headers such as `Content-Length`; the supplied
fixture mapping alone is not treated as a complete response block. Core checks
supplied fixture headers against the recorded complete observations and detects
header tampering. This remains mock evidence, not live provider proof.

After the final UI snapshot, the helper freezes the received traffic, diagnostics
and mock-recording boundaries. It completes actual response-header collection for
that finite set within the existing action deadline. Requests arriving during
collection remain queued for the next collection; cursors do not skip them.
Delayed background responses remain diagnostics, not evidence for the current
action. Missing response events or failed header reads fail and close the context;
they never turn an incomplete observation into an empty header block.

For a multi-context run, core supplies the same `MockResponseQueue` to each
`open_stepwise` call. Forward it as `mock_queue`; do not create a new queue when
switching users or replacing a session. Consumption order is global to that
projection. Core retains an independent fixture plan to verify the observed
consumption and responses. A standalone helper caller can also explicitly share
a queue; unrelated runs must use separate queues.

## Opt-in finite multi-origin HTTP

The single-origin behavior described below remains the default. A product adapter
can explicitly select `BrowserNetworkPolicy` for a page, finite APIs and static
resources served from different origins. This changes Python integration
configuration, not Scenario YAML, assertion vocabulary, or format 1.

```python
from refracto_browser import ApiEndpoint, BrowserNetworkPolicy, BrowserSupport

policy = BrowserNetworkPolicy(
    api_endpoints=(ApiEndpoint(
        origin="https://example.com:8443",
        path_prefix="/api",
        logical_prefix="",
    ),),
    resource_origins=("https://example.net:443",),
    credential_origins=("https://example.com:8443",),
)
browser = BrowserSupport(
    "https://example.com:443", read_rendered, network_policy=policy,
)
```

Here the page is on the default HTTPS port, the API is on port 8443, and static
assets may come from a separate host. `/api/records` maps to logical `records`.
The empty logical prefix owns the whole logical path space: adding an overlapping
endpoint is rejected, not resolved by request timing or response content. With
multiple services, assign disjoint logical prefixes. Prefix matching is bounded
by path segments. Do not supply `logical_path` as a second mapping mechanism.

Origins are exact scheme/host/effective-port identities. The page origin is
allowed for resources, not automatically for API evidence or credentials. API,
resource and credential permissions are independent. Additional credential header
names have explicit destination sets in `credential_headers`. The existing
authenticator supplies browser storage; this helper does not inject credentials,
perform login, or silently strip credentials to repair an unsafe configuration.
Global context authentication headers are unsuitable when any reachable origin
is outside their allowed destinations. Unsupported proxy, HTTP authentication and
client-certificate configurations fail rather than claiming untested protection.

The native Chromium collector associates requests using a per-request initiator
identity and the browser's network request ID. It adds no internal wire headers,
does not use another HTTP client to replay the request, and waits for browser
completion before accepting the response. Browser CORS and application-authored
preflights remain effective. No permissive CORS headers or disabled security
settings are supplied by the helper. Actual origin and network identity are
retained as sensitive `BrowserNetworkIdentity` metadata in the paired traffic and
recording. Core also checks the usual permit, user, session and request identities.

Explicit `no-cors` fetch mode is unsupported: debugger access to response bytes
must not turn an opaque browser response into usable evidence. Associated fetch
responses are passively drained through a clone without replacing the response
returned to the application. Native response capture has an 8 MiB limit and the
existing action deadline; over-limit data is an error, never a partial pass.

A native request without a transmitted trace has no server trace ID. Its browser
identity is sufficient for request/response association, but is not substituted
for server-side evidence. Declared trace-dependent state checks still cannot pass
without their required trace. This opt-in branch does not relax the existing
trace requirement for unmarked adapter evidence.

Finite background HTTP remains diagnostic and cannot satisfy an action's request
check. Retained diagnostics are bounded to 100 records and 256 KiB of complete
serialized records per context, including request values; truncation has a
visible note. This is not a bound on all browser memory. Payloads and credentials
are not printed in that note. A slow background request is not a reason to wait
for global network idle.

This mode still excludes streams, WebSocket, EventSource, workers/service workers,
frames/popups, redirect following, and generalized authentication flows. Native
async ownership is limited to the bounded ancestry described above; timers and
unsupported or missing async ancestry remain diagnostic. A missing
declared request remains an error even when the page loaded successfully. Mock
requests never fall through to live API services. Native mock preflight is not
supported. Complete raw response headers are unavailable for native fulfilled
mocks, so header-dependent checks cannot pass by treating fixture headers as
observed evidence. Browser-level interception rejects secondary-page/frame
requests before HTTP delivery, rather than merely closing a popup afterward.

See the [approved scope](tasks/browser-multi-origin-http.md). This mechanism guards
cooperative adapter errors and observation mix-ups, not hostile in-process code
or scripts deliberately impersonating internal browser instrumentation.

## Default single-origin transport and data boundaries

This helper supports finite HTTP responses, JSON-object request bodies and
ordinary UTF-8 URL-encoded form bodies on its existing fetch/XHR paths. It
rejects cross-origin requests, redirects, synchronous XHR, frame traffic,
workers, and streaming transports when encountered. Service workers are blocked.
Outside fetch/XHR, only GET and HEAD requests for documents, stylesheets, scripts,
images, fonts, media, text tracks, and manifests may reach the server. Other
transports, including `sendBeacon`/ping and native HTML form-navigation writes, fail before forwarding in
both modes; an empty mock plan never permits an unsupported write to fall through.
Redirects are not followed, so credentials cannot be forwarded to an unvalidated
destination. It is intended for one top-level page; browser-native application
flows beyond these bounds need a separately scoped adapter design.

### Observing ordinary form fields

The actual observed Content-Type selects form decoding:
`application/x-www-form-urlencoded`, optionally with one `charset=utf-8`
parameter. Media type and charset comparison are case-insensitive; quoted
UTF-8 and surrounding whitespace are accepted. Other parameters/charsets,
repeated charset, duplicate Content-Type rows and comma-combined ambiguous form
claims fail before forwarding or consuming a mock fixture. This is a bounded
helper policy, not a declaration that every rejected request is invalid HTTP.

Form request bytes are decoded strictly as UTF-8. Fields are separated before
percent decoding, plus represents a space, and decoding happens once. Empty
values and bare names produce empty strings; empty separators add no field.
Duplicate decoded names, empty names, malformed percent escapes and invalid
UTF-8 are rejected without replacing bytes or silently retaining one value.
Each observed field remains a string: `"0"`, `"false"` and `"null"` are not
converted to numbers, booleans or null. Dots and brackets in names stay literal;
no nested object or array convention is inferred. Existing strict request-body
checks continue to compare those actual values with Scenario expectations.

An available empty byte string represents an empty mapping. When the browser
exposes no body, evidence retains None rather than guessing an empty form.
Outside the form branch, the previous JSON-object/null decoder remains in use,
including its handling of missing and non-form Content-Type. Form-looking data
is not guessed from its contents, and a malformed form claim never falls back
to JSON. This slice does not add a general media-type conformance checker.

The live request body and Content-Type are forwarded unchanged. Complete
observed header pairs remain sensitive evidence; the existing request body is a
decoded mapping, not a retained packet capture. Mock data still comes only from
the independently supplied fixture plan. Normal action attribution, user/session
binding, background diagnostics and request/response pairing apply in both modes.
Unassigned form traffic cannot become evidence merely by matching a declaration.

There is no new YAML encoding field. An API adapter may already choose JSON or
form serialization by endpoint. Scenario describes business input; protocol
requirements such as accepting a particular media type need their own explicit
test rather than being inferred from this decoder. Multipart/file upload,
arbitrary body formats and native form navigation remain unsupported. The
[mixed JSON/form example](../examples/browser-form-requests/README.md) is loaded
and executed by real-browser tests on a public synthetic page.

Internal request-association headers are removed before traffic reaches the
server. At request start the helper generates a fresh local trace, which replaces
any application-supplied `traceparent` when the request is forwarded. Exactly one
trace header reaches the server and its value matches the recorded evidence.
Request identifiers use random bytes available on ordinary HTTP origins as well
as secure origins. The forwarded `traceparent` supplies local test correlation, including
the Demo's backend-state trace; it is not proof of independent provenance.
Instrumentation runs inside the tested browser and does not protect against a
malicious application, adapter, or normalizer.

Helper/context repr and helper error messages omit bodies, queries, header values, browser handles,
context options, bound values, selectors, and URLs. Raw port objects still hold
sensitive request/response data and are not a safe logging or export format.
The rendering callback must interpret existing UI state without clicking,
navigating, or sending requests. The helper never sends a replacement API action
to repair missing browser evidence.
