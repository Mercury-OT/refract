# Browser single-file uploads

Run from the repository root after installing the browser extra and Chromium:

```sh
python -m examples.browser_file_upload.run
python scripts/run_tests.py --output-dir /tmp/refract-browser-upload-tests -- tests/browser/test_browser_file_upload_consumers.py -q
```

The runner executes both consumers through live e2e, explicit frontend mocks,
and backend plus contract. Use `--product documents` or `--product records`, and
`--projection e2e`, `frontend`, or `backend-contract` for an individual scope.

[documents.yaml](documents.yaml) is the approved five-step flow: open, fill,
select one fixed file, separately click Upload, then GET the saved document.
The page constructs `FormData(form)` and uses native fetch. Its multipart file
field is `attachment`, with text field `title`, on `/v1/documents`.
[records.yaml](records.yaml) uses a different page, selectors, response shape,
and endpoint. Its page appends the selected File and caption to FormData and
uses asynchronous XMLHttpRequest at `/vault/records/archive/attachments`.

Selection reads the browser's actual file input for the selected-files UI
snapshot. The later uploaded-files snapshot reads visible list items created
by the product page. The adapter maps individual declared actions and does
not implement either flow. The shared browser helper observes actual native
multipart bytes; it does not substitute the selected asset for request evidence.
The server independently parses multipart, writes received bytes to temporary
files, and opens those saved files on each subsequent GET. Tests also read raw
saved payloads using a separate HTTP client.

The selection input and click's `expect.request.files` are explicit, separate
file declarations. Both use the core's frozen asset bytes. Browser selection
never reopens the local source path. The file hash pins content identity and
is not an approval claim. All five fixture files are copies of the existing
synthetic public `examples/file_upload/fixtures` assets. `sample.txt` contains
exactly `sample document` followed by LF, 16 bytes in total.

The frontend scenarios are fully authored four-step UI-only documents:
[documents-frontend.yaml](documents-frontend.yaml) and
[records-frontend.yaml](records-frontend.yaml). Their explicit JSON mock plans
return 201 and an ID. Tests require zero live API calls in this scope. They
verify selection, actual outgoing upload, and rendered response handling; they
do not claim storage readback. The full live scenarios retain their explicit
GET and are not silently shortened for frontend execution.

Backend projects the explicitly declared click request through the API driver.
It does not execute file selection or inspect the page, and its report keeps
UI obligations unchecked. Contract checks the backend recordings without
another HTTP request; these projections are not independent browser or storage
observations. Only live e2e runs all five declared operations.

`target-sources.json` pins the baseline server/page/script sources. Fault tests
change served responses through subclasses without editing those files. They
cover changed bytes, truncation, missing file, wrong field and filename, stored
corruption, and a 201 response with no saved resource. Complete observed wrong
requests and wrong stored values fail their declared checks. Missing or
malformed capture remains an evidence error.

The browser mechanism is Chromium-specific and fails when complete native
multipart segments are unavailable. It supports frozen memory-buffer selection
and finite same-page fetch/XHR. It does not claim native chooser interaction,
trusted selection events, persistence beyond immediate readback, media rendering,
or protection against hostile in-process code. The APIs, pages, credentials,
fixtures, and records here are synthetic public examples.
