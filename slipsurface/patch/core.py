"""Delta (file-by-file) self-update for a source-only installation.

When a new published release exists, the updater downloads ONLY the files
whose content changed between the running version and the release, and
copies them over the local installation in place. An inventory of every
tracked file and its SHA-256 is published alongside each release as
``manifest.json`` (or derived from the GitHub Git Trees API when a release
has no manifest asset); the updater diffs the local installation against the
target inventory and transfers just the changed/new entries. Deleted files
are removed locally. Nothing outside the application folder is touched, and
the previous state is restorable from the automatic backup.

No Qt here: this module backs the GUI updater in ``slipsurface.ui.updates``.
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
RELEASE_BASE = f"https://github.com/{REPOSITORY}/releases/download"
CHUNK = 1 << 16


def _default_open(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def _fetch_bytes(url: str, timeout: float = 30.0, opener=None) -> bytes:
    headers = {"User-Agent": f"SlipSurfaceIQ-LE/{__version__}"}
    if url.startswith(API_BASE):
        headers["Accept"] = "application/vnd.github+json"
    request = urllib.request.Request(url, headers=headers)
    try:
        with (opener or _default_open)(request, timeout) as response:  # type: ignore[attr-defined]
            return response.read()
    except urllib.error.HTTPError as exc:
        raise UpdateCheckError(f"HTTP {exc.code} for {url}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateCheckError(str(getattr(exc, "reason", exc))) from None


def _fetch_json(url: str, timeout: float = 30.0, opener=None) -> dict:
    try:
        data = json.loads(_fetch_bytes(url, timeout, opener).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise UpdateCheckError(f"invalid JSON from {url}") from None
    if not isinstance(data, dict):
        raise UpdateCheckError(f"invalid JSON from {url}")
    return data


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha_bytes(data: bytes) -> str:
    h = hashlib.sha1(f"blob {len(data)}\0".encode("ascii"))
    h.update(data)
    return h.hexdigest()


def git_blob_sha_of(path: Path) -> str:
    return git_blob_sha_bytes(path.read_bytes())


def _candidate_refs(version: str) -> tuple[str, ...]:
    v = version.strip().lstrip("v")
    return (f"v{v}", v) if v else (version.strip(),)


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
        return f"{self.from_version} → {self.to_version}: {len(self.changed)} changed, {len(self.new)} new, {len(self.removed)} removed"


def manifest_url(version: str) -> str:
    v = version.strip().lstrip("v")
    return f"{RELEASE_BASE}/v{v}/manifest.json"


def _manifest_from_git_tree(data: dict, version: str, ref: str) -> dict:
    tree = data.get("tree")
    if not isinstance(tree, list):
        raise UpdateCheckError(f"git tree of {ref} has no file table")
    files: dict[str, str] = {}
    for item in tree:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        rel = item.get("path")
        sha = item.get("sha")
        if isinstance(rel, str) and isinstance(sha, str) and is_managed(rel):
            files[rel] = sha
    if not files:
        raise UpdateCheckError(f"git tree of {ref} has no managed files")
    return {"version": version.strip().lstrip("v"), "ref": ref, "hash": "git-sha1", "files": files}


def _fetch_tree_manifest(version: str, timeout: float = 30.0, opener=None) -> dict:
    last_err: UpdateCheckError | None = None
    for ref in _candidate_refs(version):
        url = f"{API_BASE}/git/trees/{ref}?recursive=1"
        try:
            data = _fetch_json(url, timeout, opener)
            return _manifest_from_git_tree(data, version, ref)
        except UpdateCheckError as exc:
            last_err = exc
            if "404" not in str(exc):
                raise
    raise last_err or UpdateCheckError(f"manifest not found for {version}")


def fetch_manifest(version: str, timeout: float = 30.0, opener=None) -> dict:
    """The published file inventory for a release: {"files": {relpath: hash}}.

    Checks the release-asset ``manifest.json`` first (SHA-256), and falls back
    to GitHub's Git Trees API (Git blob SHA-1) when a release has no manifest
    asset attached.
    """
    last_err: UpdateCheckError | None = None
    for ref in _candidate_refs(version):
        url = f"{RELEASE_BASE}/{ref}/manifest.json"
        try:
            data = _fetch_json(url, timeout, opener)
            files = data.get("files")
            if not isinstance(files, dict):
                raise UpdateCheckError(f"manifest of {ref} has no file table")
            return data
        except UpdateCheckError as exc:
            last_err = exc
            if "404" not in str(exc):
                raise
    try:
        return _fetch_tree_manifest(version, timeout, opener)
    except UpdateCheckError:
        if last_err is not None:
            raise
        raise


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
    if old.get("hash", "sha256") != new.get("hash", "sha256"):
        old = _fetch_tree_manifest(from_version, timeout, opener)
        new = _fetch_tree_manifest(to_version, timeout, opener)
    changed, added, removed = diff_manifests(old, new)
    return UpdatePlan(from_version, to_version, changed, added, removed)


def application_root() -> Path:
    """Folder that contains main.py and the slipsurface package."""
    return Path(__file__).resolve().parents[1]


def local_hash(relpath: str, root: Path | None = None, expected_hash: str = "") -> str | None:
    root = root or application_root()
    p = root / relpath
    if not p.is_file():
        return None
    use_git_sha1 = len(expected_hash) == 40
    digest = git_blob_sha_of(p) if use_git_sha1 else sha256_of(p)
    if expected_hash and digest != expected_hash:
        data = p.read_bytes()
        if b"\r\n" in data:
            lf_data = data.replace(b"\r\n", b"\n")
            lf_digest = (
                git_blob_sha_bytes(lf_data) if use_git_sha1 else hashlib.sha256(lf_data).hexdigest()
            )
            if lf_digest == expected_hash:
                return expected_hash
    return digest


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
    target_files = {
        rel: digest
        for rel, digest in target.get("files", {}).items()
        if is_managed(rel) and isinstance(digest, str)
    }
    changed, added, removed = [], [], []
    for rel, digest in target_files.items():
        local = local_hash(rel, root, digest)
        if local is None:
            added.append(FileDelta(rel, "new", new_hash=digest))
        elif local != digest:
            changed.append(FileDelta(rel, "changed", old_hash=local, new_hash=digest))
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if (
            is_managed(rel)
            and rel not in target_files
            and not rel.startswith(KEEP_UNLISTED_PREFIXES)
        ):
            removed.append(FileDelta(rel, "removed", old_hash=sha256_of(p)))
    return UpdatePlan(__version__, to_version.strip().lstrip("v"), changed, added, removed)


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


# Folders where users may keep their own files (e.g. saved projects next to the
# examples): a file there that the target release does not list is left alone.
KEEP_UNLISTED_PREFIXES = ("examples/", "docs/")


def is_safe_relpath(relpath: str) -> bool:
    """A plain relative POSIX path inside the application folder: no absolute
    paths, drive letters, backslashes, empty, '.' or '..' components."""
    if not isinstance(relpath, str) or not relpath or "\\" in relpath or ":" in relpath:
        return False
    if relpath.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in relpath.split("/"))


def is_managed(relpath: str) -> bool:
    """Whether a repository file is part of the updatable application."""
    if not is_safe_relpath(relpath):
        return False
    parts = relpath.split("/")
    if any(part in EXCLUDED_DIRS for part in parts):
        return False
    return relpath in MANAGED_FILES or relpath.startswith(MANAGED_PREFIXES)


def download_file(
    relpath: str, version: str, dest: Path, timeout: float = 60.0, opener=None
) -> None:
    """Fetch one file of a release into dest."""
    last_err: UpdateCheckError | None = None
    for ref in _candidate_refs(version):
        url = f"{RAW_BASE}/{ref}/{relpath}"
        try:
            data = _fetch_bytes(url, timeout, opener)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return
        except UpdateCheckError as exc:
            last_err = exc
            if "404" not in str(exc):
                raise
    raise last_err or UpdateCheckError(f"HTTP 404 for {relpath}")


def backup_root(root: Path) -> Path:
    return root / ".update-backup"


def _backup_dir(root: Path, plan: UpdatePlan) -> Path:
    """A fresh backup folder for this update, e.g. .update-backup/2026.3.2-to-2026.3.3."""
    base = backup_root(root) / f"{plan.from_version}-to-{plan.to_version}"
    path, n = base, 1
    while path.exists():
        n += 1
        path = base.with_name(f"{base.name}-{n}")
    return path


def apply_update(
    plan: UpdatePlan,
    version: str,
    root: Path | None = None,
    progress: Callable[[int, int, str], bool] | None = None,
    timeout: float = 60.0,
    opener=None,
) -> str:
    """Apply a plan in place. Returns a human-readable summary.

    Every changed or new file is downloaded to a temporary folder and its hash
    verified first; the installation is touched only when all downloads are
    complete and valid. Replaced and removed files are copied to a backup
    folder for this update (``.update-backup/<from>-to-<to>``).

    ``progress(done, total, relpath)`` returning True cancels the update;
    a cancelled or failed download leaves the installation unchanged.
    """
    root = root or application_root()
    deltas = [*plan.changed, *plan.new, *plan.removed]
    unsafe = [d.relpath for d in deltas if not is_managed(d.relpath)]
    if unsafe:
        raise UpdateCheckError(f"refusing to update unexpected path(s): {', '.join(unsafe)}")
    downloads = [*plan.changed, *plan.new]
    total = len(downloads) + len(plan.removed)
    done = 0
    tmp_dir = Path(tempfile.mkdtemp(prefix="slipsurface-update-"))
    try:
        # 1) download and verify everything; the installation is not touched yet
        for delta in downloads:
            if progress is not None and progress(done, total, delta.relpath):
                raise UpdateCheckError("update cancelled")
            download_file(delta.relpath, version, tmp_dir / delta.relpath, timeout, opener)
            digest = local_hash(delta.relpath, tmp_dir, delta.new_hash) or ""
            if not plan_against_local_verifies(delta, digest):
                raise UpdateCheckError(f"hash mismatch for {delta.relpath}")
            done += 1
        # 2) back up what will be replaced or removed
        backup = _backup_dir(root, plan)
        for delta in [*downloads, *plan.removed]:
            local = root / delta.relpath
            if local.is_file():
                copy = backup / delta.relpath
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local, copy)
        # 3) install (local moves and deletes only)
        for delta in downloads:
            dest = root / delta.relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_dir / delta.relpath), dest)
        for delta in plan.removed:
            local = root / delta.relpath
            if local.is_file():
                os.remove(local)
            done += 1
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
