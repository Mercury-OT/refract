# Browser Flow: create, update, read

This runnable consumer executes three Scenarios in one live e2e Flow using the
existing synthetic records application's Promise and native async frontends.
It preserves the same user's session and browser context across all three nodes.
The target's HTML, JavaScript and API are unchanged. These are two implementations
of one example application, not two independent products or an adoption study.

From the repository root, after installing the development/browser dependencies:

```sh
uv run --locked --no-sync python -m playwright install chromium
uv run --locked --no-sync refracto validate-flow examples/browser_flow/browser.flow.yaml
uv run --locked --no-sync refracto validate-flow examples/browser_flow/browser.flow.yaml --expand
uv run --locked --no-sync python -B -m examples.browser_flow.run
```

The command runs both implementations and exits zero only if both native Flow
reports are strictly `PASSED`. Output retains Flow, Scenario, projection, Step
and check results but excludes credentials, response bodies, parameter histories
and raw error messages. A failed execution remains a failure. Use
`execute(app)` to inspect its native report and adapter diagnostics in memory.
The three target source hashes are checked before and after every execution.

## What executes

1. **Create:** open the page, fill the intended name and a run-unique code, then
   click create. Check the actual POST, response and displayed name/code. Publish
   the observed record ID and the declared code to the Flow only after success.
2. **Update:** fill the ID from the Flow, fill the independently declared updated
   name and click update. Check the PATCH, response and displayed identified
   record. Publish the intended updated name, never copy an expected name from
   the response being judged.
3. **Read:** click read, without reopening the page or refilling its ID input.
   Check the GET and returned ID/name/code against the Flow, plus the displayed
   identified record's name. This exercises retained page state across nodes.

There are exactly eight declared actions, three business requests, one named
session acquisition and one browser context open/close per successful Flow.
`on_failure: stop` blocks later nodes after a non-passing Scenario. Existing Flow
publication and invalidation rules apply; no expected value is repaired after a
failed write. The byte-pinned Scenario sidecar identifies content, not approval.

## Observation boundary

`adapter.py` reuses the existing product's authentication, normalization, target
selectors and public BrowserSupport API. Its new `records.result` mapping parses
only the actual `#result` DOM text. Its callback receives only the page and does
not read a Scenario, expected value, Flow store or cached HTTP response.
Empty initial display yields no observations;
missing/duplicate displays, nonempty hidden displays and malformed JSON are
unavailable evidence. Missing or invalid string identity stays anonymous, with
the actual field types preserved. No ID is guessed or copied from traffic.

Response and rendered content are different observations of the same application,
not independent database evidence. The normal records endpoints do not test
authorization rules: session reuse here proves execution continuity, not access
control. Sample mapping tests address mistakes and do not defend against hostile
same-process adapter code. See the [threat model](../../docs/threat-model.md).

The focused tests use labeled, isolated faults for incorrect displayed content,
an update acknowledgement that does not persist, missing identity and failed
publication. They do not edit the normal target or change approved expectations.
The example adds no YAML shape, core feature, private adapter or environment
provisioning mechanism.
