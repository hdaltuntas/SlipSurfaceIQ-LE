"""Version and source-only entrypoint invariants."""

import re
from pathlib import Path

from slipsurface import __version__

ROOT = Path(__file__).resolve().parents[1]
OBSOLETE = (
    ".github/workflows/packages.yml",
    "packaging/README.md",
    "packaging/build.py",
    "packaging/entry.py",
    "packaging/linux/PKGBUILD",
    "packaging/linux/slipsurface.desktop",
    "packaging/linux/slipsurface.spec.in",
    "packaging/requirements.txt",
    "packaging/slipsurface.spec",
    "packaging/smoke.py",
    "run_windows.bat",
    "run_linux_mac.sh",
    "slipsurface/__main__.py",
    "slipsurface/patch/__main__.py",
)


def test_calendar_version_matches_readme_and_release_notes():
    assert re.fullmatch(r"20\d{2}\.\d+\.\d+", __version__)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert f"— version {__version__}" in readme.split("SlipSurfaceIQ LE is", 1)[0]
    assert f"[{__version__} release notes](RELEASE_NOTES.md)" in readme
    assert notes.startswith(f"# SlipSurfaceIQ LE {__version__}\n")
    assert "format version 3" in readme


def test_main_py_is_the_only_supported_application_entrypoint():
    assert (ROOT / "main.py").is_file()
    assert (ROOT / "requirements.txt").is_file()
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "windows-latest" not in ci
    assert "test-distro" not in ci
    assert "python main.py" in ci
    for path in OBSOLETE:
        assert not (ROOT / path).exists(), f"Obsolete package/launcher: {path}"
    assert not list((ROOT / "slipsurface").rglob("__main__.py"))
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[build-system]" not in config
    assert "[project.gui-scripts]" not in config
    assert "[project.scripts]" not in config
    assert "python main.py" in (ROOT / "README.md").read_text(encoding="utf-8")
