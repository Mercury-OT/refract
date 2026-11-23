# Background reports during a document change

## Scope and acceptance

A user can open a second document in the same tab and authenticated browser
context. A departing document can submit an optional report using
`navigator.sendBeacon`. Chromium can pause this HTTP request without providing a
Network identifier. A repeatable two-open control isolates the failure from the
business action. The maintenance work covers the optional native browser helper.
The Scenario declaration, runner and target application keep their existing
interfaces.

Support only explicitly configured, finite, exact same-origin report paths in
live mode, as non-evidence. Restrict eligibility to the main frame, an ordinary
open navigation, HTTP POST and the browser Ping resource class. Require normal
credential, transport and redirect policy. Default deny and mock isolation
remain effective. Never synthesize a network identity, claim the report as a
business request, expose its data in diagnostics, or discard unrelated integrity
failures. Handle only the specific loss of an optional old-document background
response body if demonstrated necessary; loss of required foreground evidence
remains visible. Use a bounded diagnostic reason.

Verify with a neutral real-browser page with and without a departure report.
Exercise matching, wrong destination or path, wrong phase/frame/type, redirects,
mock isolation and the independence of a real business POST. Record baseline,
controls, independent audit and acceptance. Publish only source, synthetic
fixtures and reviewed aggregates.

## Verification and acceptance

Before the repair both real Chromium controls with a departure beacon failed
on the second open; the plain controls reopened successfully. With the exact
path enabled, real navigation exposed a separate loss of an optional response
body from the departing document. The helper verifies that its replacement
document has committed before treating that specific protocol failure as a
diagnostic.

Development ran 81 focused cases. Independent audit passed 34 repository
regressions, 11 real Chromium controls and 14 event controls covering the
old-document distinction. A real target produced both fresh snapshots in six
out of six repeated double opens. This measures navigation only. Architect
acceptance passed for the optional browser helper.
