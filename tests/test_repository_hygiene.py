import subprocess
from pathlib import Path

import pytest


HYGIENE_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_repository_hygiene.sh"
)


def _check_url(tmp_path, url):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "probe.txt").write_text(url, encoding="utf-8")
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "add", "probe.txt"],
        cwd=repository,
        check=True,
    )
    return subprocess.run(
        ["bash", str(HYGIENE_SCRIPT)],
        cwd=repository,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://pypi.org/simple",
        "https://files.pythonhosted.org/packages/example.whl",
    ],
)
def test_hygiene_allows_official_python_package_hosts(tmp_path, url):
    result = _check_url(tmp_path, url)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "url",
    [
        "https" + "://pypi.org.evil.invalid/private",
        "https" + "://files.pythonhosted.org.evil.invalid/private",
    ],
)
def test_hygiene_rejects_hosts_with_allowlisted_prefixes(tmp_path, url):
    result = _check_url(tmp_path, url)

    assert result.returncode == 1
    assert "outside the public allow-list" in result.stderr
