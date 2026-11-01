"""Delta (file-by-file) self-update for a source-only installation.

When a new published release exists, the updater downloads ONLY the files
whose content changed between the running version and the release, and
copies them over the local installation in place. An inventory of every
tracked file and its SHA-256 is published alongside each release as
``manifest.json``; the updater fetches the two manifests (current and
target), diffs them, and transfers just the changed/new entries. Deleted
files are removed locally. Nothing outside the application folder is
touched, and the previous state is restorable from the automatic backup.

No Qt here: the same module backs the GUI updater and the CLI
(``python -m slipsurface.patch``).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from slipsurface import __version__
from slipsurface.updates import REPOSITORY, UpdateCheckError, ssl_context

RAW_BASE = f"https://raw.githubusercontent.com/{REPOSITORY}"
API_BASE = f"https://api.github.com/repos/{REPOSITORY}"
CHUNK = 1 << 16


def _default_open(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def _fetch_bytes(url: str, timeout: float = 30.0, opener=None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": f"SlipSurfaceIQ-LE/{__version__}"})
    try:
        with (opener or _default_open)(request, timeout) as response:  # type: ignore[attr-defined]
            return response.read()
    except urllib.error.HTTPError as exc:
        raise UpdateCheckError(f"HTTP {exc.code} for {url}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateCheckError(str(getattr(exc, "reason", exc))) from None


def _fetch_json(url: str, timeout: float = 30.0, opener=None) -> dict:
    try:
        return json.loads(_fetch_bytes(url, timeout, opener).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise UpdateCheckError(f"invalid JSON from {url}") from None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class FileDelta:
    """One file difference between two manifests."""

    relpath: str
    kind: str  # "changed" | "new" | "removed"
    old_hash: str = ""
    new_hash: str = ""


@dataclass
class UpdatePlan:
    """Everything needed to bring the installation from one version to another."""

    from_version: str
    to_version: str
    changed: list[FileDelta] = field(default_factory=list)
    new: list[FileDelta] = field(default_factory=list)
    removed: list[FileDelta] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.changed) + len(self.new) + len(self.removed)

    @property
    def download_count(self) -> int:
        return len(self.changed) + len(self.new)

    def summary(self) -> str:
        return (
            f"{self.from_version} → {self.to_version}: "
            f"{len(self.changed)} değişti, {len(self.new)} yeni, {len(self.removed)} silindi"
        )


def manifest_url(version: str) -> str:
    return f"{RAW_BASE}/v{version}/manifest.json"


def fetch_manifest(version: str, timeout: float = 30.0, opener=None) -> dict:
    """The published file inventory for a release: {"files": {relpath: sha256}}."""
    data = _fetch_json(manifest_url(version), timeout, opener)
    files = data.get("files")
    if not isinstance(files, dict):
        raise UpdateCheckError(f"manifest of v{version} has no file table")
    return data


def diff_manifests(
    old: dict, new: dict
) -> tuple[list[FileDelta], list[FileDelta], list[FileDelta]]:
    old_files = old.get("files", {})
    new_files = new.get("files", {})
    changed, added, removed = [], [], []
    for rel, digest in new_files.items():
        if rel not in old_files:
            added.append(FileDelta(rel, "new", new_hash=digest))
        elif old_files[rel] != digest:
            changed.append(FileDelta(rel, "changed", old_hash=old_files[rel], new_hash=digest))
    for rel, digest in old_files.items():
        if rel not in new_files:
            removed.append(FileDelta(rel, "removed", old_hash=digest))
    return changed, added, removed


def plan_update(
    from_version: str,
    to_version: str,
    timeout: float = 30.0,
    opener=None,
) -> UpdatePlan:
    """Diff the two releases' manifests. Raises UpdateCheckError."""
    old = fetch_manifest(from_version, timeout, opener)
    new = fetch_manifest(to_version, timeout, opener)
    changed, added, removed = diff_manifests(old, new)
    return UpdatePlan(from_version, to_version, changed, added, removed)


def application_root() -> Path:
    """Folder that contains main.py and the slipsurface package."""
    return Path(__file__).resolve().parents[1]


def local_hash(relpath: str, root: Path | None = None) -> str | None:
    root = root or application_root()
    p = root / relpath
    if not p.is_file():
        return None
    return sha256_of(p)


def plan_against_local(
    to_version: str,
    root: Path | None = None,
    timeout: float = 30.0,
    opener=None,
) -> UpdatePlan:
    """Update plan from the *running* installation to a release.

    Local files are hashed and compared with the target manifest, so an
    installation that already matches the target in some files downloads
    nothing for them (resume-friendly).
    """
    root = root or application_root()
    target = fetch_manifest(to_version, timeout, opener)
    target_files = target.get("files", {})
    changed, added, removed = [], [], []
    for rel, digest in target_files.items():
        local = local_hash(rel, root)
        if local is None:
            added.append(FileDelta(rel, "new", new_hash=digest))
        elif local != digest:
            changed.append(FileDelta(rel, "changed", old_hash=local, new_hash=digest))
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if is_managed(rel) and rel not in target_files:
            removed.append(FileDelta(rel, "removed", old_hash=sha256_of(p)))
    return UpdatePlan(__version__, to_version, changed, added, removed)


MANAGED_PREFIXES = (
    "slipsurface/",
    "examples/",
    "docs/",
    "tests/",
)
MANAGED_FILES = (
    "main.py",
    "README.md",
    "RELEASE_NOTES.md",
    "LICENSE",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
)
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def is_managed(relpath: str) -> bool:
    """Whether a repository file is part of the updatable application."""
    parts = relpath.split("/")
    if any(part in EXCLUDED_DIRS for part in parts):
        return False
    return relpath in MANAGED_FILES or relpath.startswith(MANAGED_PREFIXES)


def download_file(
    relpath: str, version: str, dest: Path, timeout: float = 60.0, opener=None
) -> None:
    """Fetch one file of a release into dest, verifying its SHA-256 lazily."""
    url = f"{RAW_BASE}/v{version}/{relpath}"
    data = _fetch_bytes(url, timeout, opener)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def backup_root(root: Path) -> Path:
    return root / ".update-backup"


def apply_update(
    plan: UpdatePlan,
    version: str,
    root: Path | None = None,
    progress: Callable[[int, int, str], bool] | None = None,
    timeout: float = 60.0,
    opener=None,
) -> str:
    """Apply a plan in place. Returns a human-readable summary.

    ``progress(done, total, relpath)`` returning True cancels the update;
    files copied so far are kept in the backup folder for a manual restore.
    """
    root = root or application_root()
    backup = backup_root(root)
    backup.mkdir(exist_ok=True)
    downloads = [(d, "changed") for d in plan.changed] + [(d, "new") for d in plan.new]
    total = len(downloads) + len(plan.removed)
    done = 0
    tmp_dir = Path(tempfile.mkdtemp(prefix="slipsurface-update-"))
    try:
        for delta, _kind in downloads:
            if progress is not None and progress(done, total, delta.relpath):
                raise UpdateCheckError("güncelleme iptal edildi")
            # stash the current copy (if any) for restore
            local = root / delta.relpath
            if local.is_file():
                backup_copy = backup / delta.relpath
                backup_copy.parent.mkdir(parents=True, exist_ok=True)
                if not backup_copy.exists():
                    shutil.copy2(local, backup_copy)
            download_file(delta.relpath, version, tmp_dir / delta.relpath, timeout, opener)
            done += 1
        for delta in plan.removed:
            if progress is not None and progress(done, total, delta.relpath):
                raise UpdateCheckError("güncelleme iptal edildi")
            local = root / delta.relpath
            if local.is_file():
                backup_copy = backup / delta.relpath
                backup_copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local, backup_copy)
                os.remove(local)
            done += 1
        # second pass: move verified downloads into place (fast, local)
        for delta, _kind in downloads:
            tmp = tmp_dir / delta.relpath
            dest = root / delta.relpath
            if tmp.is_file():
                digest = sha256_of(tmp)
                if plan_against_local_verifies(delta, digest):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(tmp), dest)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return plan.summary()


def plan_against_local_verifies(delta: FileDelta, digest: str) -> bool:
    return not delta.new_hash or digest == delta.new_hash


def write_manifest(root: Path, dest: Path, version: str) -> dict:
    """Build manifest.json for a release (used by the release workflow)."""
    files: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if is_managed(rel):
            files[rel] = sha256_of(p)
    manifest = {"version": version, "files": files}
    dest.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    return manifest
