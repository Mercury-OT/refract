"""Two unchanged synthetic pages, native uploads, and independent saved bytes."""
import hashlib
from http.client import HTTPConnection
from urllib.parse import urlsplit

import pytest
import yaml

from examples.browser_file_upload.app import Application, application
from examples.browser_file_upload.run import ROOT, execute, verify_frozen_targets
from examples.file_upload.server import UploadStore


PRODUCTS = ("documents", "records")
FILE_FIELDS = {"documents": "attachment", "records": "blob"}
API_PATHS = {"documents": "/v1/documents", "records": "/vault/records/archive/attachments"}


@pytest.fixture(autouse=True)
def unchanged_consumer_sources():
    paths = [p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    before = {p: p.read_bytes() for p in paths}
    verify_frozen_targets()
    yield
    assert {p: p.read_bytes() for p in paths} == before
    verify_frozen_targets()


def step(report, identity, domain=0):
    return next(s for s in report.domains[domain].steps if s.step_id == identity)


def evidence(bundle, identity):
    return next(item for item in bundle.ui.evidence if item.step_id == identity)


def assert_closed(bundle):
    assert bundle.auth.session_calls == 1
    assert bundle.ui.opened_contexts == bundle.ui.closed_contexts == 1


def saved_payload(app, product, identifier):
    # Independent HTTP read, not a Refract API driver, recorder, or selected File.
    address = urlsplit(app.base_url)
    connection = HTTPConnection(address.hostname, address.port, timeout=5)
    suffix = "/content" if product == "documents" else "/payload"
    try:
        connection.request("GET", API_PATHS[product] + "/" + identifier + suffix,
                           headers={"x-upload-session": "example-editor"})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("product", PRODUCTS)
def test_full_browser_upload_reads_actual_selected_submitted_and_saved_file(product):
    with application() as app:
        report, bundle = execute(app, product)
        assert report.status == "PASSED", report.localize()
        assert [s.status for s in report.domains[0].steps] == [
            "COMPLETED", "COMPLETED", "PASSED", "PASSED", "PASSED"]
        selected = step(report, "choose_attachment").file_selection
        assert selected.target_matches == 1
        assert selected.file.filename == "sample.txt"
        assert selected.file.data == b"sample document\n"
        choice = evidence(bundle, "choose_attachment")
        click = evidence(bundle, "submit_attachment")
        assert choice.rendered[product + ".selected_files"]["anonymous"] == [
            {"fields": {"filename": "sample.txt", "size": 16}}]
        assert choice.rendered[product + ".uploaded_files"]["anonymous"] == []
        assert choice.traffic == []
        assert all(item.traffic == [] for item in bundle.ui.evidence[:-1])
        assert click.rendered[product + ".uploaded_files"]["anonymous"] == [
            {"fields": {"filename": "sample.txt"}}]
        assert len(click.traffic) == 1
        actual = click.traffic[0].request.files[FILE_FIELDS[product]]
        assert actual.data == app.submissions[0].files[FILE_FIELDS[product]][1] == b"sample document\n"
        assert actual.sha256 == hashlib.sha256(app.submissions[0].files[FILE_FIELDS[product]][1]).hexdigest()
        assert len(app.store.received) == len(app.submissions) == 1
        identifier = next(iter(app.store.entries))[1]
        assert saved_payload(app, product, identifier) == (200, b"sample document\n")
        assert bundle.api.calls == [("GET", API_PATHS[product] + "/" + identifier)]
        assert {item.user for item in bundle.ui.evidence} == {"editor"}
        assert len({item.context_id for item in bundle.ui.evidence}) == 1
        assert len({item.session_generation for item in bundle.ui.evidence}) == 1
        assert_closed(bundle)
    assert app.closed


@pytest.mark.parametrize("product", PRODUCTS)
def test_frontend_authored_ui_scenario_has_zero_live_api_traffic(product):
    with application() as app:
        report, bundle = execute(app, product, projections=("frontend",))
        assert report.status == "PASSED", report.localize()
        assert len(report.domains[0].steps) == 4
        assert app.store.request_count == 0
        assert app.submissions == app.store.received == []
        assert bundle.api.calls == []
        click = evidence(bundle, "submit_attachment")
        assert len(click.traffic) == len(click.mock_recordings) == 1
        assert click.traffic[0].request.files[FILE_FIELDS[product]].data == b"sample document\n"
        assert click.rendered[product + ".uploaded_files"]["anonymous"] == [
            {"fields": {"filename": "sample.txt"}}]
        assert_closed(bundle)
    assert app.closed


@pytest.mark.parametrize("product", PRODUCTS)
def test_backend_and_contract_project_declared_click_without_browser_selection(product):
    with application() as app:
        report, bundle = execute(app, product, projections=("backend", "contract"))
        assert report.status == "PASSED", report.localize()
        assert len(report.domains) == 2
        assert bundle.ui.opened_contexts == bundle.ui.closed_contexts == 0
        assert bundle.ui.evidence == []
        assert bundle.api.calls == [("POST", API_PATHS[product]), ("GET", API_PATHS[product] + "/1")]
        assert len(app.store.received) == 1
        assert app.store.received[0].data == b"sample document\n"
        assert app.store.request_count == 2  # Contract issues no second upload/read.
        selection = step(report, "choose_attachment")
        assert selection.file_selection is None
        assert selection.status == "NOT_APPLICABLE"
        assert selection.not_checked == ["UI action/checks are outside backend projection"]
        contract = report.domains[1]
        assert contract.not_checked == ["choose_attachment: file selection is outside contract scope"]
        assert all(s.file_selection is None for s in contract.steps)
    assert app.closed


def mutation_app(kind):
    class Mutated(Application):
        def script(self, product):
            source = super().script(product).decode()
            field = FILE_FIELDS[product]
            changes = {
                "wrong_bytes": f"body.set('{field}', new File(['incorrect bytes'], input.files[0].name));",
                "truncate": f"body.set('{field}', new File([input.files[0].slice(0, 5)], input.files[0].name));",
                "drop": f"body.delete('{field}');",
                "wrong_field": f"body.delete('{field}'); body.append('other_file', input.files[0]);",
                "wrong_filename": f"body.set('{field}', input.files[0], 'different.txt');",
            }
            point = "const response = await fetch" if product == "documents" else "return new Promise"
            assert source.count(point) == 1
            return source.replace(point, changes[kind] + "\n  " + point).encode()
    return Mutated


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("kind", ("wrong_bytes", "truncate", "drop", "wrong_field", "wrong_filename"))
def test_complete_wrong_browser_upload_is_failed_not_missing_evidence(product, kind):
    with application(app_type=mutation_app(kind)) as app:
        report, bundle = execute(app, product)
        assert report.status == "FAILED", report.localize()
        assert step(report, "choose_attachment").status == "PASSED"
        submitted = step(report, "submit_attachment")
        assert submitted.status == "FAILED", report.localize()
        assert any(c.check == "request" and c.ok is False for c in submitted.checks)
        assert report.domains[0].steps[-1].status == "BLOCKED"
        assert bundle.api.calls == []
        assert len(app.submissions) == 1
        observed = evidence(bundle, "submit_attachment").traffic[0].request.files
        server_files = app.submissions[0].files
        assert (None if not server_files else {k: (v.filename, v.data) for k, v in observed.items()}) == (server_files or None)
        if kind == "drop":
            assert observed is None
        elif kind == "wrong_field":
            assert set(observed) == {"other_file"}
        elif kind == "wrong_filename":
            assert observed[FILE_FIELDS[product]].filename == "different.txt"
        else:
            expected = b"incorrect bytes" if kind == "wrong_bytes" else b"sampl"
            assert observed[FILE_FIELDS[product]].data == expected
        assert_closed(bundle)
    assert app.closed


@pytest.mark.parametrize("product", PRODUCTS)
def test_mock_success_cannot_hide_wrong_actual_upload_bytes(product):
    with application(app_type=mutation_app("wrong_bytes")) as app:
        report, bundle = execute(app, product, projections=("frontend",))
        assert report.status == "FAILED", report.localize()
        assert step(report, "submit_attachment").status == "FAILED"
        assert any(c.check == "request" and not c.ok for c in step(report, "submit_attachment").checks)
        assert app.store.request_count == 0
        assert app.submissions == []
        assert bundle.api.calls == []
        assert evidence(bundle, "submit_attachment").traffic[0].request.files[FILE_FIELDS[product]].data == b"incorrect bytes"
        assert_closed(bundle)


class CorruptedStore(UploadStore):
    def save_upload(self, product, title, filename, data):
        return super().save_upload(product, title, filename, b"corrupt saved bytes")


class FalseCreatedStore(UploadStore):
    def save_upload(self, product, title, filename, data):
        return "missing-resource"


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("store_factory", (CorruptedStore, FalseCreatedStore))
def test_201_with_wrong_or_missing_saved_bytes_fails_later_read(product, store_factory):
    with application(store_factory=store_factory) as app:
        report, bundle = execute(app, product)
        assert report.status == "FAILED", report.localize()
        assert step(report, "submit_attachment").status == "PASSED"
        final = report.domains[0].steps[-1]
        assert final.status == "FAILED"
        assert any(not c.ok for c in final.checks)
        assert app.store.received[0].data == b"sample document\n"
        identifier = "1" if store_factory is CorruptedStore else "missing-resource"
        status, body = saved_payload(app, product, identifier)
        if store_factory is CorruptedStore:
            assert (status, body) == (200, b"corrupt saved bytes")
        else:
            assert status == 404
        assert_closed(bundle)
    assert app.closed


def variant_scenario(tmp_path, product, asset_name):
    document = yaml.safe_load((ROOT / (product + ".yaml")).read_text())
    data = (ROOT / "fixtures" / asset_name).read_bytes()
    (tmp_path / "fixtures").mkdir(exist_ok=True)
    (tmp_path / "fixtures" / asset_name).write_bytes(data)
    descriptor = {"path": "fixtures/" + asset_name, "sha256": hashlib.sha256(data).hexdigest()}
    document["steps"][2]["file"] = dict(descriptor)
    document["steps"][2]["expect"]["ui"][0]["value"] = asset_name
    document["steps"][3]["expect"]["request"]["files"] = {FILE_FIELDS[product]: dict(descriptor)}
    document["steps"][3]["expect"]["ui"][0]["value"] = asset_name
    document["steps"][4]["expect"]["response"] = [
        {"check": "status_equals", "value": 200},
        {"check": "field_equals", "field": "filename", "value": asset_name},
        {"check": "field_equals", "field": "size", "value": len(data)},
        {"check": "field_equals", "field": "sha256", "value": descriptor["sha256"]},
    ]
    path = tmp_path / "variant.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return path, data


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("asset_name", ("bytes.bin", "empty.bin", "pixel.png", "page.pdf"))
def test_actual_binary_empty_png_pdf_browser_bytes_equal_independent_storage(tmp_path, product, asset_name):
    path, original = variant_scenario(tmp_path, product, asset_name)
    with application() as app:
        report, bundle = execute(app, product, scenario_path=path)
        assert report.status == "PASSED", report.localize()
        selected = step(report, "choose_attachment").file_selection.file
        submitted = evidence(bundle, "submit_attachment").traffic[0].request.files[FILE_FIELDS[product]]
        assert selected.data == submitted.data == app.store.received[0].data == original
        assert saved_payload(app, product, "1") == (200, original)
        if asset_name == "empty.bin":
            assert submitted.data == b""
            assert submitted.filename == "empty.bin"
        assert_closed(bundle)
    assert app.closed
