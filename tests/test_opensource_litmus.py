import pathlib
import shutil
import subprocess
import sys
import tempfile

import refracto


def test_core_imports_without_adapters():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    snippet = """
import importlib
import sys

modules_to_import = [
    'refracto.declaration.model',
    'refracto.declaration.loader',
    'refracto.declaration.vocabulary',
    'refracto.ports',
    'refracto.asyncwait',
    'refracto.grid',
    'refracto.contract.store',
    'refracto.projection.backend',
    'refracto.projection.frontend',
    'refracto.projection.e2e',
    'refracto.projection.contract',
    'refracto.recorder',
    'refracto.report',
    'refracto.runner',
    'refracto.cli',
]

for module_name in modules_to_import:
    importlib.import_module(module_name)

bad = [m for m in sys.modules if m == 'adapters' or m.startswith('adapters.')]
assert not bad, f'core must not import adapters, but found: {bad}'
"""
    result = subprocess.run([sys.executable, "-c", snippet], cwd=repo_root, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"Subprocess import check failed.\n"
        f"Return code: {result.returncode}\n"
        f"stderr: {result.stderr}\n"
        f"stdout: {result.stdout}"
    )


def test_core_source_has_no_adapters_import():
    root = pathlib.Path(refracto.__file__).parent
    offenders = [
        str(path)
        for path in root.rglob("*.py")
        if ("import adapters" in (src := path.read_text(encoding="utf-8")) or "from adapters" in src)
    ]
    assert offenders == [], f"core files importing adapters: {offenders}"


def test_core_tests_survive_without_scenarios_or_adapters_dir():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        isolated_root = pathlib.Path(tmp)
        (isolated_root / "tests" / "fixtures").mkdir(parents=True)
        shutil.copy2(repo_root / "tests" / "fixtures" / "synthetic_scenario.yaml",
                     isolated_root / "tests" / "fixtures" / "synthetic_scenario.yaml")
        shutil.copy2(repo_root / "tests" / "__init__.py", isolated_root / "tests" / "__init__.py")
        shutil.copy2(repo_root / "tests" / "fakes.py", isolated_root / "tests" / "fakes.py")

        assert not (isolated_root / "scenarios").exists()
        assert not (isolated_root / "adapters").exists()

        snippet = """
import os

assert not os.path.exists('scenarios')
assert not os.path.exists('adapters')

from refracto import ports
from refracto.declaration.loader import load_scenario
from refracto.projection import backend
from tests.fakes import FakeAuth, FakeApi, FakeNormalizer, FakeRecorder, FakeStateProbe

s = load_scenario('tests/fixtures/synthetic_scenario.yaml')
assert s.id == 'refracto.synthetic_probe'

def _resolver(scenario, step, template):
    return ports.RequestSpec(method=template.method, path=template.path, body={})

api = FakeApi(responses={('POST', 'resource/action'): {'status': 200, 'json': {'success': True, 'data': {'taskId': 'T1'}}}})
state = FakeStateProbe()
state.observe = lambda tid: ports.StateFacts(tid, [
    ports.Span('POST /resource/action'),
    ports.Span('INSERT resource.job_queue'),
])

res = backend.run(s, auth=FakeAuth(), api=api, state=state, recorder=FakeRecorder(),
                  resolve_request=_resolver, normalizer=FakeNormalizer())
assert res.passed, f'expected backend projection to pass, got: {res.checks}'
print('OK')
"""
        result = subprocess.run([sys.executable, "-c", snippet], cwd=isolated_root,
                                capture_output=True, text=True)
        assert result.returncode == 0, (
            f"core test logic failed without scenarios/ or adapters/ on disk.\n"
            f"Return code: {result.returncode}\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
        assert "OK" in result.stdout
