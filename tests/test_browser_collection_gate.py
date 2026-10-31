"""Optional browser collection is scoped to this repository's browser suite."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests import conftest


@pytest.mark.parametrize("relative_path,ignored", [
    ("test_binding.py", None),
    ("test_browser_support_lifecycle.py", None),
    ("browser", True),
    ("browser/test_support.py", True),
    ("browser_like/test_case.py", None),
])
def test_browser_named_checkout_ancestor_does_not_hide_core_tests(
        tmp_path, monkeypatch, relative_path, ignored):
    tests_directory = tmp_path / "browser" / "refract" / "tests"
    monkeypatch.setattr(conftest, "_TESTS_DIRECTORY", tests_directory)
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda name: None)
    assert conftest.pytest_ignore_collect(tests_directory / relative_path, None) is ignored


def test_browser_suite_collects_when_its_optional_dependency_exists(tmp_path, monkeypatch):
    tests_directory = tmp_path / "browser" / "refract" / "tests"
    monkeypatch.setattr(conftest, "_TESTS_DIRECTORY", tests_directory)
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda name: object())
    assert conftest.pytest_ignore_collect(tests_directory / "browser" / "test_support.py", None) is None


def test_browser_directory_outside_this_repository_is_not_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(conftest, "_TESTS_DIRECTORY", tmp_path / "refract" / "tests")
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda name: None)
    assert conftest.pytest_ignore_collect(tmp_path / "other" / "tests" / "browser" / "test_case.py", None) is None


@pytest.mark.parametrize("options,dependencies,browser_expected,demo_expected", [
    ((), True, True, True),
    (("--ignore=tests/browser",), True, False, True),
    (("--ignore-glob=tests/browser/*",), True, False, True),
    ((), False, False, False),
])
def test_collection_gate_preserves_pytest_exclusions(
        tmp_path, options, dependencies, browser_expected, demo_expected):
    """Run pytest's real hook chain without collecting the repository recursively."""
    tests = tmp_path / "tests"
    (tests / "browser").mkdir(parents=True)
    source = Path(conftest.__file__).read_text(encoding="utf-8")
    # Override this copied module's binding, not the shared importlib module.
    # Dependency availability is controlled even in a dev-only environment.
    source += (
        "\nfrom types import SimpleNamespace\n"
        "importlib = SimpleNamespace(util=SimpleNamespace(\n"
        f"    find_spec=lambda name: object() if {dependencies!r} else None))\n"
    )
    (tests / "conftest.py").write_text(source, encoding="utf-8")
    (tests / "test_core.py").write_text("def test_core(): pass\n", encoding="utf-8")
    (tests / "browser" / "test_browser.py").write_text(
        "def test_browser(): pass\n", encoding="utf-8")
    (tests / "test_demo_app.py").write_text("def test_demo(): pass\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=",
         "--confcutdir", str(tmp_path), *options, "tests"],
        cwd=tmp_path, text=True, capture_output=True, timeout=10,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": ""},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/test_core.py::test_core" in result.stdout
    assert ("tests/browser/test_browser.py::test_browser" in result.stdout) is browser_expected
    assert ("tests/test_demo_app.py::test_demo" in result.stdout) is demo_expected
