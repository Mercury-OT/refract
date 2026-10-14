"""Collection gates for optional browser and Demo adapter tests.

The demo reference adapter (`adapters/demo/`) and its test infrastructure
(`tests/demo/`, `tests/test_demo_app.py`) depend on the optional `demo` extra
(fastapi / uvicorn / playwright / httpx). Under a bare `pip install -e ".[dev]"`
those imports are absent, and `tests/demo/conftest.py` imports httpx at module
load — which would abort collection for the whole directory.

So when the demo dependencies are not importable, pytest skips collecting the
entire demo suite. This keeps the core offline suite runnable with only the
`dev` extra, preserving the guarantee that the product-agnostic core needs no
product or browser dependencies.

The independent tests/browser suite needs only the browser extra. Its offline
lifecycle checks remain outside that directory and always collect.
"""
import importlib.util
from pathlib import Path


_TESTS_DIRECTORY = Path(__file__).resolve().parent


def _has_demo_deps() -> bool:
    required = ["httpx", "fastapi", "uvicorn", "playwright"]
    return all(importlib.util.find_spec(name) is not None for name in required)


def pytest_ignore_collect(collection_path, config):
    path = str(collection_path)
    browser_related = collection_path.resolve().is_relative_to(_TESTS_DIRECTORY / "browser")
    if browser_related and importlib.util.find_spec("playwright") is None:
        return True
    demo_related = (
        f"tests{__import__('os').sep}demo{__import__('os').sep}" in path
        or path.endswith(f"tests{__import__('os').sep}test_demo_app.py")
    )
    if demo_related and not _has_demo_deps():
        return True
    return False
