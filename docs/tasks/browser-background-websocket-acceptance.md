# Local verification: background WebSockets

Scope: the [approved specification](browser-background-websocket.md) on base
`e02897d7`. This record describes evidence, not a release or submission.
Architect acceptance: PASS for the specified scope, 2026-11-21.

## Maintainer summary

- A live Chromium page can use one configured same-origin background socket.
- No configuration means no connection; a mock context neither connects nor
  tells its page that a connection succeeded.
- Background frames and their unrelated HTTP callbacks cannot satisfy an action.
- Normal trust checks apply. Bounds, denials and context cleanup are tested.
- Navigation and a visible UI control are not verification of a complete business flow.

## What was checked

The independent audit ran 49 policy and browser checks and an overlapping
117-check regression selection. It also tested simultaneous connections, bursts
of uncaught denials and a fault during refusal. Defects found before acceptance
were fixed: refusal no longer stalls the browser event loop, repeated identical
page errors retain a bounded category without hiding the first error, and a
failed close cannot return normally to the routing library's simulated-open path.

Two trusted and two untrusted TLS trials were run in an isolated Linux browser
environment: the trusted peer received a real upgrade and echoed the test value;
the untrusted peer received zero upgrades and the client observed an error.
Normal verification was enabled; no machine-wide trust was changed. To repeat
inside a disposable Linux Docker container with Chromium, Playwright, OpenSSL
and certutil installed:

```sh
python -B -m tests.browser.verify_background_websocket_tls
```

With the final helper and a pinned, unmodified web application, two fresh
browser-context comparisons independently established a real upgrade, arrival
at the intended page and exactly one visible input control. The default helper
refused before handshake. The enabled navigation produced zero primary HTTP
records. This was an authenticated page-navigation gate; no message creation,
delivery or cross-user business verdict was tested. Raw evidence, accounts,
logs and application-specific configuration are not included here.

The full installed-extras collection was covered in local regression shards:
5,834 tests outside the browser directory (one existing dependency warning),
722 and 577 browser tests, and one late-added close-failure control from the
final 49-test panel. The union covers all 7,134 distinct collected tests; the
panels are not counted twice. Dev-only Python 3.11 and 3.12 runs each passed
5,737 tests with one optional skip. Lock, whitespace and repository hygiene
checks passed, including hygiene over the new files. No core, YAML, target
product, or application adapter changes are part of this delivery.
