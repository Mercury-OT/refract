# Mixed JSON and ordinary form requests

[`mixed_requests.yaml`](mixed_requests.yaml) uses the existing Scenario format.
It opens the public synthetic browser page, fills one value, then submits that
value to a JSON endpoint and a form endpoint. Each response must report the
submitted value. Neither the Scenario nor the browser adapter supplies encoding
instructions to the page; the page owns each endpoint's transport choice.

The executable consumer is `tests/browser/test_form_requests.py`, using
`tests/browser/app.html`, its local HTTP peer and the existing `SyntheticUi`
adapter. Run from the repository root with the browser dependencies and
Playwright Chromium installed:

```sh
uv run --locked --no-sync refracto validate examples/browser-form-requests/mixed_requests.yaml
uv run --locked --no-sync pytest tests/browser/test_form_requests.py -q
```

The same loaded YAML runs through frontend mock and live e2e projections. The
mock plan supplies independent responses; it never contacts the API. Live tests
also inspect bytes and Content-Type received by the local server. This proves
the tested transport behavior, not a new Scenario assertion about encoding or
private-product adoption. Contract is not selected by this UI example and is
not an independent request observer.

For ordinary URL-encoded forms, observed fields remain strings. For example,
use `"0"` or `"false"` when that is what the page sends; JSON numeric `0` and
boolean `false` remain different values. Repeated field names, invalid encoding
and unsupported form Content-Type declarations fail visibly. No defaults or
types are inferred from assertions. See [browser support](../../docs/browser-support.md)
for the complete observation boundary, including native form-navigation limits.

A product's API adapter can already choose JSON or form serialization by
endpoint. This example adds no required encoding field to Scenario and no new
port. The optional browser helper now observes supported form traffic that was
previously rejected by its JSON-only request decoder.
