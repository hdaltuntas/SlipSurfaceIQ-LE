"""Ensure app, metadata and current package documentation share one version.

The release workflow derives filename and MSI version from __version__.
A release label alone does not change the files in a build.
"""

import re
import subprocess
import sys
from pathlib import Path

from slipsurface import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_calendar_version_is_the_build_version():
    result = subprocess.run(
        [sys.executable, str(ROOT / "packaging" / "build.py"), "version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == __version__
    assert re.fullmatch(r"20\d{2}\.\d+\.\d+", __version__)


def test_release_docs_show_the_actual_application_version():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert f"— version {__version__}" in readme.split("SlipSurfaceIQ LE is", 1)[0]
    assert f"[{__version__} release notes](RELEASE_NOTES.md)" in readme
    assert notes.startswith(f"# SlipSurfaceIQ LE {__version__}\n")
    assert "version 3" in notes.split("# SlipSurfaceIQ LE 2026.1.6", 1)[0]


def test_native_package_install_names_match_application_version():
    install = (ROOT / "packaging" / "README.md").read_text(encoding="utf-8")
    names = (
        f"SlipSurfaceIQ-LE-{__version__}-windows-x64.msi",
        f"slipsurface-iq-le_{__version__}-1_ubuntu24.04_amd64.deb",
        f"slipsurface-iq-le-{__version__}-1.fedora.x86_64.rpm",
        f"slipsurface-iq-le-{__version__}-1.opensuse.x86_64.rpm",
        f"slipsurface-iq-le-{__version__}-1-x86_64.pkg.tar.zst",
    )
    for name in names:
        assert name in install, name
    # Current installer documentation should not silently retain prior
    # filenames even though historical release notes are preserved.
    assert set(re.findall(r"20\d{2}\.\d+\.\d+", install)) == {__version__}
    major, minor, patch = map(int, __version__.split("."))
    assert f"`{major - 2000}.{minor}.{patch}`" in install
