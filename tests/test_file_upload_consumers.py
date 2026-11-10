"""Real multipart receipt and saved-file readback, independent of driver echoes."""

from copy import deepcopy
from dataclasses import fields, replace
import hashlib
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from adapters.file_upload.adapter import (
    ExampleAuthenticator, UploadApiDriver, build_adapters, encode_multipart,
)
from examples.file_upload.server import UploadStore, serve_uploads
from refracto.runner import run_scenario
from refracto.ports import RecordedResponse, NormalizedResponse


EXAMPLES = Path(__file__).resolve().parents[1] / "examples/file_upload"
FIXTURES = ("sample.txt", "pixel.png", "page.pdf", "bytes.bin", "empty.bin")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_raw(origin, product, identifier):
    """A separate HTTP client reads storage without the framework adapter."""
    address = urlsplit(origin)
    connection = HTTPConnection(address.hostname, address.port, timeout=5)
    route = (f"/v1/documents/{identifier}/content" if product == "documents"
             else f"/vault/records/archive/attachments/{identifier}/payload")
    try:
        connection.request("GET", route, headers={"x-upload-session": "example-editor"})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def fixture_scenario(tmp_path, product, name):
    data = (EXAMPLES / "fixtures" / name).read_bytes()
    source = tmp_path / name
    source.write_bytes(data)
    declaration = yaml.safe_load((EXAMPLES / (product + ".yaml")).read_text())
    field_name = "attachment" if product == "documents" else "blob"
    declaration["steps"][0]["do"]["request"]["files"][field_name] = {
        "path": name, "sha256": digest(data)}
    metadata_checks = declaration["steps"][1]["expect"]["response"]
    metadata_checks[:] = [check for check in metadata_checks if check.get("field") != "content"]
    for check in metadata_checks:
        if check.get("field") in {"filename", "size", "sha256"}:
            check["value"] = {"filename": name, "size": len(data), "sha256": digest(data)}[check["field"]]
    scenario = tmp_path / "upload.yaml"
    scenario.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    return scenario, source, data


@pytest.mark.parametrize("product", ["documents", "records"])
def test_public_upload_examples_parse_multipart_and_read_saved_bytes(product):
    with serve_uploads() as (origin, store):
        report = run_scenario(EXAMPLES / (product + ".yaml"), build_adapters(origin, product),
                              projections=("backend", "contract"))
        assert report.status == "PASSED"
        assert {domain.status for domain in report.domains} == {"PASSED"}
        assert store.request_count == 2
        assert len(store.received) == 1  # Contract performs no additional send.
        received = store.received[0]
        assert received.product == product
        assert received.field_name == ("attachment" if product == "documents" else "blob")
        assert received.filename == "sample.txt"
        assert received.data == b"sample document\n"
        recording = report.domains[0].provider_recordings[0]
        assert recording.request_header_items == list(received.request_headers)
        assert dict(received.request_headers)["traceparent"] == recording.request.traceparent
        assert received.text_fields == ({"title": "Example attachment"} if product == "documents"
                                        else {"caption": "Archive attachment"})
        saved = next(iter(store.entries.values()))["path"]
        assert saved.read_bytes() == received.data
        identifier = report.domains[0].provider_recordings[1].request.path.rsplit("/", 1)[-1]
        assert read_raw(origin, product, identifier) == (200, received.data)


@pytest.mark.parametrize("product", ["documents", "records"])
@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_binary_and_empty_assets_reach_server_and_saved_byte_assertions(tmp_path, product, name, projections):
    scenario, _, original = fixture_scenario(tmp_path, product, name)
    with serve_uploads() as (origin, store):
        report = run_scenario(scenario, build_adapters(origin, product), projections=projections)
        assert report.status == "PASSED"
        assert store.request_count == 2
        assert len(store.received) == 1
        assert store.received[0].data == original
        assert store.received[0].filename == name
        assert read_raw(origin, product, "1") == (200, original)
        recorded = report.domains[0].provider_recordings[-1]
        observed = build_adapters(origin, product).normalizer.normalize(recorded).fields
        assert observed["sha256"] == digest(original)
        assert observed["size"] == len(original)


class ChangedWireDriver(UploadApiDriver):
    """Lie about the sent file by recording the unchanged intended RequestSpec."""

    def __init__(self, origin, mutation):
        super().__init__(origin)
        self.mutation = mutation

    def _encode_upload(self, request):
        files, body = deepcopy(request.files), deepcopy(request.body)
        field_name, asset = next(iter(files.items()))
        if self.mutation == "truncate":
            files[field_name] = replace(asset, data=asset.data[:-1])
        elif self.mutation == "replace":
            files[field_name] = replace(asset, data=b"x" * len(asset.data))
        elif self.mutation == "drop_file":
            files.clear()
        elif self.mutation == "wrong_field":
            files = {"unexpected": asset}
        elif self.mutation == "drop_text":
            body.clear()
        elif self.mutation == "rename":
            files[field_name] = replace(asset, filename="different.bin")
        return encode_multipart(body, files)


@pytest.mark.parametrize("product", ["documents", "records"])
@pytest.mark.parametrize("mutation", ["truncate", "replace", "drop_file", "wrong_field", "drop_text", "rename"])
def test_wrong_bytes_and_missing_fields_fail_despite_intended_metadata_echo(tmp_path, product, mutation):
    scenario, _, original = fixture_scenario(tmp_path, product, "bytes.bin")
    with serve_uploads() as (origin, store):
        adapter = build_adapters(origin, product, driver=ChangedWireDriver(origin, mutation))
        report = run_scenario(scenario, adapter, projections=("backend", "contract"))
        assert report.status == "FAILED"
        assert {domain.status for domain in report.domains} == {"FAILED"}
        recordings = report.domains[0].provider_recordings
        intended = next(iter(recordings[0].request.files.values()))
        assert intended.data == original
        assert intended.sha256 == digest(original)
        assert intended.filename == "bytes.bin"
        if mutation in {"truncate", "replace", "rename"}:
            assert recordings[0].status == 201
            assert report.domains[0].steps[0].status == "PASSED"
            assert report.domains[0].steps[1].status == "FAILED"
            if mutation != "rename":
                assert store.received[0].data != original
                observed = adapter.normalizer.normalize(recordings[-1]).fields
                assert observed["sha256"] != digest(original)
                assert read_raw(origin, product, "1")[1] != original
            else:
                assert store.received[0].filename == "different.bin"
        else:
            assert recordings[0].status == 422
            assert report.domains[0].steps[0].status == "FAILED"
            assert store.received == []


class FalseSuccessStore(UploadStore):
    def save_upload(self, product, title, filename, data):
        return "missing"  # Deliberately return an id without saving any bytes.


class CorruptSavedStore(UploadStore):
    def save_upload(self, product, title, filename, data):
        identifier = super().save_upload(product, title, filename, data)
        self.entries[(product, identifier)]["path"].write_bytes(b"corrupted storage")
        return identifier


@pytest.mark.parametrize("product", ["documents", "records"])
@pytest.mark.parametrize("store_factory", [FalseSuccessStore, CorruptSavedStore])
def test_successful_upload_response_requires_actual_later_saved_bytes(tmp_path, product, store_factory):
    scenario, _, original = fixture_scenario(tmp_path, product, "pixel.png")
    with serve_uploads(store_factory=store_factory) as (origin, store):
        report = run_scenario(scenario, build_adapters(origin, product), projections=("backend", "contract"))
        assert report.status == "FAILED"
        assert {domain.status for domain in report.domains} == {"FAILED"}
        assert store.received[0].data == original
        assert report.domains[0].steps[0].status == "PASSED"
        assert report.domains[0].steps[1].status == "FAILED"
        assert report.domains[0].provider_recordings[0].status == 201
        expected_status = 404 if store_factory is FalseSuccessStore else 200
        assert report.domains[0].provider_recordings[-1].status == expected_status


def test_source_replacement_after_load_cannot_change_the_http_upload(tmp_path):
    scenario, source, original = fixture_scenario(tmp_path, "documents", "page.pdf")

    class ReplacingAuthenticator(ExampleAuthenticator):
        def session(self, user):
            source.write_bytes(b"changed after scenario was loaded")
            return super().session(user)

    with serve_uploads() as (origin, store):
        adapter = build_adapters(origin)
        adapter.auth = ReplacingAuthenticator()
        report = run_scenario(scenario, adapter, projections=("backend", "contract"))
        assert report.status == "PASSED"
        assert source.read_bytes() != original
        assert store.received[0].data == original
        assert read_raw(origin, "documents", "1") == (200, original)


def test_sender_preserves_non_ascii_and_quoted_asset_basename(tmp_path):
    original = b"unchanged\x00\xff"
    name = 'asset "quoted" café.bin'
    (tmp_path / name).write_bytes(original)
    declaration = yaml.safe_load((EXAMPLES / "documents.yaml").read_text())
    declaration["steps"][0]["do"]["request"]["files"]["attachment"] = {
        "path": name, "sha256": digest(original)}
    declaration["steps"][1]["expect"]["response"] = [
        {"check": "status_equals", "value": 200},
        {"check": "field_equals", "field": "filename", "value": name},
        {"check": "field_equals", "field": "sha256", "value": digest(original)},
    ]
    scenario = tmp_path / "quoted.yaml"
    scenario.write_text(yaml.safe_dump(declaration), encoding="utf-8")
    with serve_uploads() as (origin, store):
        report = run_scenario(scenario, build_adapters(origin), projections=("backend", "contract"))
        assert report.status == "PASSED"
        assert store.received[0].filename == name
        assert store.received[0].data == original


@pytest.mark.parametrize("product", ["documents", "records"])
@pytest.mark.parametrize("projections", [("backend", "contract"), ("e2e",)])
def test_real_saved_file_readback_keeps_sensitive_values_out_of_default_repr(tmp_path, product, projections):
    name = "private-filename-sentinel.txt"
    content = "private-content-sentinel"
    data = content.encode("utf-8")
    (tmp_path / name).write_bytes(data)
    declaration = yaml.safe_load((EXAMPLES / (product + ".yaml")).read_text())
    field_name = "attachment" if product == "documents" else "blob"
    declaration["steps"][0]["do"]["request"]["files"][field_name] = {
        "path": name, "sha256": digest(data)}
    declaration["steps"][1]["expect"]["response"] = [
        {"check": "status_equals", "value": 200},
        {"check": "field_equals", "field": "filename", "value": name},
        {"check": "field_equals", "field": "content", "value": content},
    ]
    scenario = tmp_path / "private-readback.yaml"
    scenario.write_text(yaml.safe_dump(declaration), encoding="utf-8")
    with serve_uploads() as (origin, store):
        adapter = build_adapters(origin, product)
        report = run_scenario(scenario, adapter, projections=projections)
        assert report.status == "PASSED"
        assert store.received[0].filename == name
        assert read_raw(origin, product, "1") == (200, data)
        raw = report.domains[0].provider_recordings[-1]
        normalized = adapter.normalizer.normalize(raw)
        # Explicit data access remains available; repr is not serialization.
        assert name in raw.text and content in raw.text
        assert name in str(raw.json) and content in str(raw.json)
        assert normalized.fields["filename"] == name
        assert normalized.fields["content"] == content
        assert normalized.raw is raw
        for value in (report, raw, normalized):
            assert name not in repr(value)
            assert content not in repr(value)
        for model, names in ((RecordedResponse, {"json", "text"}),
                             (NormalizedResponse, {"fields", "raw"})):
            for item in fields(model):
                if item.name in names:
                    assert item.repr is False
                    assert item.metadata["sensitive"] is True
