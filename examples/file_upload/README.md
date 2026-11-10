# Fixed file uploads over HTTP

Run from the repository root with the ordinary development dependencies:

```sh
python -m examples.file_upload.run
python scripts/run_tests.py --output-dir /tmp/refract-upload-tests -- tests/test_file_upload_consumers.py -q
```

`documents.yaml` sends `fixtures/sample.txt` as multipart field `attachment` to
the Documents API. `records.yaml` sends the same asset as `blob` to the unrelated
Records attachment route. They have different text fields and response shapes.
The standard-library sender shares one transport path for backend and explicit
API actions in live e2e. API actions in e2e are not browser upload evidence.

The server independently parses incoming multipart, saves the received bytes to
a temporary file, and rereads that file on later GET requests. Metadata hashes
come from saved bytes. A separate test HTTP client reads the saved raw payload;
it does not reuse the upload descriptor or framework recordings.
The tests compare raw server receipts and raw later HTTP response bodies with
the original fixtures, including synthetic text, PNG, PDF, binary and empty
files. Corruption, dropped fields, and a false 201 are failing controls even
when the driver records unchanged intended request metadata.

The file descriptor's hash pins its identity; it does not confer approval.
Core freezes verified bytes at load time and never asks the sender to reopen
a filename. File paths are relative to the declaring Scenario. The host owns
file budgets; YAML adds no MIME setting, encoding or filename override.
`refracto.files.FileConfig(max_file_bytes=10 * 1024 * 1024,
max_total_bytes=64 * 1024 * 1024)` gives the defaults. Pass `file_config=` to
the loader or runner to configure them. Both limits are strict positive
integers. One loaded Scenario/Flow counts each canonical source pathname once;
different paths, including hard links, count separately.

These synthetic consumers demonstrate transport and immediate saved-byte
readback only. They do not establish image rendering, PDF preview, video
playback, import behavior, long-term durability or real-product adoption.
Contract replays provider recordings without another upload and is not an
independent observation of HTTP or storage. In-process adapters remain
cooperative code, not a sandboxed trust boundary.

All fixtures are synthetic public examples. `sample.txt` is exactly 16 bytes
(`sample document` plus LF); `pixel.png` is a 1×1 RGB PNG, and `page.pdf` is a
minimal one-page PDF. `bytes.bin` contains non-text bytes; `empty.bin` is empty.
