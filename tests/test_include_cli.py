"""Expansion is explicit, read-only, and shares the runtime loader."""
import json

from refracto.cli import main
from tests.test_scenario_include import include, parent, write_bundle


def test_expansion_prints_complete_symbolic_plan(tmp_path, capsys):
    path, _ = write_bundle(tmp_path)
    assert main(["validate", str(path), "--expand"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["scenario"] == "example.parent"
    assert output["steps"][0]["id"] == "setup/create"
    assert output["steps"][0]["source"]["scenario_id"] == "shared.create"


def test_normal_validation_does_not_dump_include_values(tmp_path, capsys):
    sentinel = "INCLUDE-SENSITIVE-SENTINEL"
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"name": sentinel}})]))
    assert main(["validate", str(path)]) == 0
    assert sentinel not in str(capsys.readouterr())
    assert main(["validate", str(path), "--expand"]) == 0
    assert sentinel in capsys.readouterr().out


def test_invalid_expansion_has_no_partial_stdout(tmp_path, capsys):
    path, child = write_bundle(tmp_path)
    child.write_text(child.read_text() + "\n# drift\n")
    assert main(["validate", str(path), "--expand"]) == 2
    assert capsys.readouterr().out == ""


def test_expansion_distinguishes_literal_reference_like_dictionary(tmp_path, capsys):
    path, _ = write_bundle(tmp_path, parent([include(**{"with": {"name": {"from_parameter": "payload"}}})],
        parameters={"payload": {"from_step": "not-a-reference", "response_field": "id"}}))
    assert main(["validate", str(path), "--expand"]) == 0
    first = capsys.readouterr().out
    document = json.loads(first)
    assert document["parameters"]["payload"]["kind"] == "object"
    assert document["parameters"]["payload"]["entries"]["from_step"] == {"kind": "literal", "value": "not-a-reference"}
    assert document["steps"][0]["do"]["request"]["body"]["entries"]["name"]["kind"] == "reference"
    assert main(["validate", str(path), "--expand"]) == 0
    assert capsys.readouterr().out == first


def test_expansion_help_discloses_confidentiality(capsys):
    import pytest
    with pytest.raises(SystemExit) as result:
        main(["validate", "--help"])
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert "confidentiality" in output and "runtime bindings" in output


def test_expansion_exposes_public_aliases_and_verified_symbolic_sources(tmp_path, capsys):
    from tests.test_scenario_named_results import bundle
    path, child = bundle(tmp_path)
    assert main(["validate", str(path), "--expand"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["results"] == {}
    assert output["included_results"] == {"setup": {
        "record_id": {"from_step": "setup/create", "response_field": "id"},
        "record_name": {"from_step": "setup/create", "response_field": "name"}}}
    assert output["steps"][-1]["do"]["request"]["path"][1] == {
        "kind": "reference", "from_step": "setup/create", "response_field": "id"}
    assert main(["validate", str(child), "--expand"]) == 0
    standalone = json.loads(capsys.readouterr().out)
    assert standalone["results"]["record_id"] == {"from_step": "create", "response_field": "id"}


def test_bad_named_result_expansion_never_emits_partial_plan(tmp_path, capsys):
    from tests.test_scenario_named_results import bundle, include, named, request
    path, _ = bundle(tmp_path, steps=[include(), request("read", body={"id": named("not_exported")})])
    assert main(["validate", str(path), "--expand"]) == 2
    assert capsys.readouterr().out == ""
