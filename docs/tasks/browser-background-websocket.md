# Bounded background WebSocket compatibility

Status: specification approved for local implementation and independent review.

## Purpose and contract

Let a live top-level page keep a background connection without admitting any new
source of action, HTTP, state, or contract evidence. The opt-in belongs to the
native Chromium helper's Python network policy, not the Scenario or its adapter's
business assertions. Default and mock contexts deny before a real connection or
a synthetic open. Keep other transports, core, Scenario YAML and product code
unchanged.

- Configure an exact same-origin endpoint (scheme, host, effective port, exact
  path), explicitly allowed query keys and bounded plain values. Reject duplicates,
  unknown keys, userinfo, fragments, nonempty subprotocols and ambiguous encodings;
  do not rewrite requests to make them acceptable. Require explicit credential
  destination permission, retain normal TLS verification, and allow cleartext only
  at loopback. The helper does not add credentials or follow redirects.
- Install both constructor and context-level admission before product navigation.
  Do not rely on a socket event after transmission. Restrict permission to the
  owned page's top document. No permissions for subframes, other windows, workers,
  redirected destinations or unconfigured pages.
- Bound active connections and lifetime admissions per context, including reconnects.
  Refusals are visible framework errors; do not fabricate an open, wait for network
  idle, record message contents, or log URLs, query values or credentials. Close
  connections when the owning context ends, including failure.
- The socket itself produces no primary traffic or recordings. An HTTP request made
  by a message handler must not satisfy a click's declared request, even on the
  same endpoint. Conversely, an HTTP action legitimately resumed after waiting for
  a notification still requires its own existing proof. Background traffic does
  not lower any existing missing-evidence or whole-page error gate.

## Acceptance gates

1. Use neutral browser/server controls to observe real handshakes, bidirectional
   delivery and disconnects, including trusted WSS and untrusted-certificate denial.
   Neither changing host trust nor bypassing certificate verification is acceptable.
2. Test default and mock (no upstream handshake **and** no open), exact matches and
   rejected destinations, query shapes, credential restrictions, subprotocol,
   redirect, subframe/new window, connection and retry limits, disposal and error
   cleanup. Check diagnostic bounds and absence of sensitive values.
3. Use an independent observation of HTTP recipients to separate socket callbacks
   from action continuations. Verify that unassociated traffic never fills a
   primary slot. Exercise actual Chromium, not only policy predicates.
4. Run regressions and an independent review. Repeat a pinned real page navigation
   with the shipping helper, without instrumentation that changes its behavior;
   distinguish document arrival, actual upgrade and visible UI from business
   acceptance. Keep product-specific configuration and raw evidence local.

This is not a WebSocket assertion or mocking API, multi-origin streaming support,
a throughput claim, or a sandbox for arbitrary hostile code.
