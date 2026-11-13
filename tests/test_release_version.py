"""The installed app and its installer must identify the same release."""

from pathlib import Path
import re
import tomllib

from parqcel import __version__


def test_package_app_and_windows_installer_versions_agree():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    installer = (root / "installer/parqcel.iss").read_text(encoding="utf-8")
    match = re.search(r"^AppVersion=(.+)$", installer, re.MULTILINE)
    assert match is not None
    assert metadata["project"]["version"] == __version__ == match[1].strip()
