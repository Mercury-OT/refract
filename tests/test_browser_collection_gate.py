"""Optional browser collection is scoped to this repository's browser suite."""

import pytest

from tests import conftest


@pytest.mark.parametrize("relative_path,ignored", [
    ("test_binding.py", False),
    ("test_browser_support_lifecycle.py", False),
    ("browser", True),
    ("browser/test_support.py", True),
    ("browser_like/test_case.py", False),
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
    assert conftest.pytest_ignore_collect(tests_directory / "browser" / "test_support.py", None) is False


def test_browser_directory_outside_this_repository_is_not_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(conftest, "_TESTS_DIRECTORY", tmp_path / "refract" / "tests")
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda name: None)
    assert conftest.pytest_ignore_collect(tmp_path / "other" / "tests" / "browser" / "test_case.py", None) is False
