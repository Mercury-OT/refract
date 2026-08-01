"""Collection gate for the demo-adapter tests.

The demo reference adapter (`adapters/demo/`) and its test infrastructure
(`tests/demo/`, `tests/test_demo_app.py`) depend on the optional `demo` extra
(fastapi / uvicorn / playwright / httpx). Under a bare `pip install -e ".[dev]"`
those imports are absent, and `tests/demo/conftest.py` imports httpx at module
load — which would abort collection for the whole directory.

So when the demo dependencies are not importable, pytest skips collecting the
entire demo suite. This keeps the core offline suite runnable with only the
`dev` extra, preserving the guarantee that the product-agnostic core needs no
product or browser dependencies.
"""
import importlib.util


def _has_demo_deps() -> bool:
    required = ["httpx", "fastapi", "uvicorn", "playwright"]
    return all(importlib.util.find_spec(name) is not None for name in required)


def pytest_ignore_collect(collection_path, config):
    path = str(collection_path)
    demo_related = (
        f"tests{__import__('os').sep}demo{__import__('os').sep}" in path
        or path.endswith(f"tests{__import__('os').sep}test_demo_app.py")
    )
    if demo_related and not _has_demo_deps():
        return True
    return False
