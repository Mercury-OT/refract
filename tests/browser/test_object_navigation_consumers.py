"""Live full-document consumers with frozen normal targets and explicit faults."""
import json

import pytest

from examples.ui_object_navigation.app import Application
from examples.ui_object_navigation.run import ROOT, SCENARIO, run_case, target_hashes, verify_frozen_targets
from refracto.declaration.loader import load_scenario


def step(row, identity):
    return next(item for item in row['steps'] if item['id'] == identity)


def requests(row, method, path):
    return [item for item in row['server_requests'] if item['method'] == method and item['path'] == path]


def evidence(row, identity):
    return next(item for item in row['browser_evidence'] if item['step'] == identity)


@pytest.mark.parametrize('implementation', ['anchor', 'location'])
def test_same_scenario_navigates_edits_and_reads_the_selected_object(implementation):
    row = run_case(implementation)
    assert row['status'] == 'PASSED', row['steps']
    assert row['degradation'] == []
    assert row['closed_contexts'] == row['browser_context_count'] == row['session_calls'] == 1
    assert {item['user'] for item in row['browser_evidence']} == {'editor'}
    assert len({item['session_generation'] for item in row['browser_evidence']}) == 1
    assert [item['id'] for item in row['records']] == ['r1', 'r2', 'r3']
    assert [item['name'] for item in row['records']] == ['First record', 'Second record', 'Updated record']
    assert step(row, 'open_editor')['selection'] == {
        'object_id': 'r3', 'object_matches': 1, 'control_matches': 1}
    assert len(requests(row, 'POST', '/api/records')) == 1
    assert len(requests(row, 'GET', '/records/r3/edit')) == 1
    assert len(requests(row, 'GET', '/api/records/r3')) == 2  # Startup plus explicit final read.
    assert len(requests(row, 'PATCH', '/api/records/r3')) == 1
    # No destination document or startup fetch is credited to the click.
    assert evidence(row, 'open_editor')['traffic'] == []
    assert evidence(row, 'save')['traffic'] == [{'method': 'PATCH', 'path': 'records/r3'}]
    diagnostic = [request for item in row['browser_evidence'] for request in item['diagnostic_requests']]
    assert {'method': 'GET', 'path': 'records/r3'} in diagnostic
    assert not requests(row, 'PATCH', '/api/records/r1')
    assert not requests(row, 'PATCH', '/api/records/r2')


class WrongDestination(Application):
    def editor_page(self, identity):
        if identity == 'r3':
            self.faults_applied = ['wrong-destination-object']
            return super().editor_page('r1')
        return super().editor_page(identity)


@pytest.mark.parametrize('implementation', ['anchor', 'location'])
def test_correct_selection_does_not_hide_wrong_destination_object(implementation):
    row = run_case(implementation, app_type=WrongDestination)
    assert row['status'] != 'PASSED', row['steps']
    assert row['target_faults'] == ['wrong-destination-object']
    selected = step(row, 'open_editor')
    assert selected['status'] == 'FAILED'
    assert selected['selection']['object_id'] == 'r3'
    assert {'point': 'frontend', 'check': 'object_field_equals', 'ok': False} in selected['checks']
    assert step(row, 'fill_name')['status'] == step(row, 'save')['status'] == 'BLOCKED'
    assert len(requests(row, 'GET', '/records/r3/edit')) == 1
    assert not any(item['method'] == 'PATCH' for item in row['server_requests'])
    assert row['records'][2]['name'] == 'Example record'
    assert row['closed_contexts'] == 1


class WrongSave(Application):
    def script(self):
        source = super().script().decode()
        original = "const response = await fetch(editor.getAttribute('action'), {"
        assert source.count(original) == 1
        self.faults_applied = ['wrong-save-object']
        return source.replace(original, "const response = await fetch('/api/records/r1', {").encode()


@pytest.mark.parametrize('implementation', ['anchor', 'location'])
def test_new_document_wrong_save_is_not_repaired_or_reported_as_correct(implementation):
    row = run_case(implementation, app_type=WrongSave)
    assert row['status'] != 'PASSED', row['steps']
    assert row['target_faults'] == ['wrong-save-object']
    assert step(row, 'open_editor')['status'] == 'PASSED'
    assert step(row, 'save')['status'] == 'ERROR'
    assert step(row, 'read_again')['status'] == 'BLOCKED'
    assert len(requests(row, 'PATCH', '/api/records/r1')) == 1
    assert not requests(row, 'PATCH', '/api/records/r3')
    assert row['records'][0]['name'] == 'Updated record'  # Actual damage is disclosed, not undone.
    assert row['records'][2]['name'] == 'Example record'
    assert row['closed_contexts'] == 1


def test_normal_navigation_targets_remain_frozen_and_scenario_retains_existing_shape():
    verify_frozen_targets()
    assert target_hashes() == json.loads((ROOT / 'target-sources.json').read_text())['sha256']
    scenario = load_scenario(SCENARIO)
    assert [item.id for item in scenario.steps] == [
        'create', 'open_list', 'open_editor', 'fill_name', 'save', 'read_again']
    assert scenario.steps[2].request is None
    for name in ('app.py', 'editor.js'):
        assert 'data-' not in (ROOT / name).read_text()


@pytest.mark.parametrize('implementation', ['anchor', 'location'])
def test_destination_bootstrap_cannot_satisfy_a_declared_click_api_request(tmp_path, implementation):
    import yaml
    from refracto.runner import run_scenario
    from examples.ui_object_navigation.adapter import adapters
    from examples.ui_object_navigation.app import application

    document = yaml.safe_load(SCENARIO.read_text())
    navigation = document['steps'][2]
    navigation['expect']['request'] = {
        'method': 'GET', 'path': ['records', {'from_step': 'create', 'response_field': 'id'}]}
    navigation['expect']['response'] = [{'check': 'status_equals', 'value': 200}]
    path = tmp_path / 'bootstrap-is-not-action.yaml'
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    verify_frozen_targets()
    with application(implementation) as app:
        bound = adapters(app)
        report = run_scenario(path, bound, projections=('e2e',))
        steps = {item.step_id: item for domain in report.domains for item in domain.steps}
        assert report.status != 'PASSED'
        assert steps['open_editor'].status == 'ERROR'
        assert steps['save'].status == 'BLOCKED'
        observed = next(item for item in bound.ui.evidence if item.step_id == 'open_editor')
        assert observed.object_selection.object_id == 'r3'
        assert observed.traffic == []
        assert any(item['method'] == 'GET' and item['path'] == '/api/records/r3'
                   for item in app.received)
        assert not any(item['method'] == 'PATCH' for item in app.received)
    verify_frozen_targets()
