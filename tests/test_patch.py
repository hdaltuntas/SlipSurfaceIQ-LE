"""Delta (changed-files-only) updater tests: manifest diff, apply, restore."""

import hashlib
import json

import pytest

from slipsurface.patch import (
    FileDelta,
    UpdatePlan,
    apply_update,
    diff_manifests,
    is_managed,
    plan_against_local,
    sha256_of,
    write_manifest,
)
from slipsurface.updates import UpdateCheckError


# ------------------------------------------------------------ classification
@pytest.mark.parametrize(
    "rel,managed",
    [
        ("main.py", True),
        ("README.md", True),
        ("requirements.txt", True),
        ("slipsurface/lem/bishop.py", True),
        ("examples/acads_1a.slp.json", True),
        ("docs/SHANSEP.md", True),
        (".git/config", False),
        (".venv/bin/python", False),
        ("slipsurface/__pycache__/x.pyc", False),
        ("random.txt", False),
    ],
)
def test_managed_files(rel, managed):
    assert is_managed(rel) is managed


# ---------------------------------------------------------------- manifest
def test_write_manifest_hashes_managed_files(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "slipsurface").mkdir()
    (tmp_path / "slipsurface" / "core.py").write_text("x = 1")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git")
    dest = tmp_path / "manifest.json"
    manifest = write_manifest(tmp_path, dest, "2026.3.0")
    files = manifest["files"]
    assert "main.py" in files and "slipsurface/core.py" in files
    assert ".git/config" not in files
    assert files["main.py"] == sha256_of(tmp_path / "main.py")
    # the manifest itself is not part of the payload
    assert dest.read_text().startswith("{")
    json.loads(dest.read_text())


# -------------------------------------------------------------------- diff
def test_diff_manifests_changed_new_removed():
    old = {"files": {"a.py": "h1", "b.py": "h2", "c.py": "h3"}}
    new = {"files": {"a.py": "h1", "b.py": "h2new", "d.py": "h4"}}
    changed, added, removed = diff_manifests(old, new)
    assert [d.relpath for d in changed] == ["b.py"]
    assert [d.relpath for d in added] == ["d.py"]
    assert [d.relpath for d in removed] == ["c.py"]
    assert changed[0].old_hash == "h2" and changed[0].new_hash == "h2new"


def test_diff_manifests_identical():
    m = {"files": {"a.py": "h1"}}
    changed, added, removed = diff_manifests(m, m)
    assert not changed and not added and not removed


# ------------------------------------------------------------- plan + apply
class FakeNet:
    """opener that serves release files from a dict of {relpath: bytes}."""

    def __init__(self, files):
        self.files = files
        self.fetched = []

    def __call__(self, request, timeout):
        url = request.full_url
        self.fetched.append(url)
        rel = url.split("/v2026.3.0/", 1)[-1] if "/v2026.3.0/" in url else ""
        payload = self._serve(url, rel)
        return FakeResponse(payload)

    def _serve(self, url, rel):
        if url.endswith("manifest.json"):
            return json.dumps(
                {
                    "version": "2026.3.0",
                    "files": {k: sha256_bytes(v) for k, v in self.files.items()},
                }
            ).encode()
        if rel in self.files:
            return self.files[rel]
        raise UpdateCheckError(f"404 {rel}")


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_plan_update_downloads_nothing_matching(tmp_path, monkeypatch):
    # local installation identical to the target manifest
    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_text("v3")
    (root / "slipsurface" / "x.py").write_text("x")
    net = FakeNet({"main.py": b"v3", "slipsurface/x.py": b"x"})
    monkeypatch.setattr("slipsurface.patch.core.application_root", lambda: root)
    plan = plan_against_local("2026.3.0", root=root, opener=net)
    assert plan.total == 0
    assert not net.fetched or all(u.endswith("manifest.json") for u in net.fetched)


def test_apply_update_copies_only_changed_files(tmp_path, monkeypatch):
    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_text("old")
    (root / "slipsurface" / "keep.py").write_text("keep")
    (root / "slipsurface" / "drop.py").write_text("drop")
    net = FakeNet(
        {
            "main.py": b"new",
            "slipsurface/keep.py": b"keep",
            "slipsurface/added.py": b"added",
        }
    )
    plan = UpdatePlan(
        "2026.2.0",
        "2026.3.0",
        changed=[FileDelta("main.py", "changed", old_hash="x", new_hash=sha256_bytes(b"new"))],
        new=[FileDelta("slipsurface/added.py", "new", new_hash=sha256_bytes(b"added"))],
        removed=[FileDelta("slipsurface/drop.py", "removed")],
    )
    summary = apply_update(plan, "2026.3.0", root=root, opener=net)
    assert (root / "main.py").read_text() == "new"
    assert (root / "slipsurface" / "keep.py").read_text() == "keep"
    assert (root / "slipsurface" / "added.py").read_text() == "added"
    assert not (root / "slipsurface" / "drop.py").exists()
    # backups of the replaced files were kept
    backup = root / ".update-backup"
    assert (backup / "main.py").read_text() == "old"
    assert (backup / "slipsurface" / "drop.py").read_text() == "drop"
    assert "1 değişti" in summary or "değişti" in summary
    # only the two changed files were downloaded
    file_fetches = [u for u in net.fetched if not u.endswith("manifest.json")]
    assert len(file_fetches) == 2


def test_apply_update_progress_cancel(tmp_path):
    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_text("old")
    net = FakeNet({"main.py": b"new"})
    plan = UpdatePlan(
        "2026.2.0",
        "2026.3.0",
        changed=[FileDelta("main.py", "changed", new_hash=sha256_bytes(b"new"))],
    )
    with pytest.raises(UpdateCheckError):
        apply_update(
            plan, "2026.3.0", root=root, opener=net, progress=lambda d, t, r: True
        )  # cancel immediately
    # the local file was not replaced (backup only)
    assert (root / "main.py").read_text() == "old"


def test_local_hash_ignores_extra_files(tmp_path):
    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_text("v3")
    (root / "notes.txt").write_text("not managed")  # outside the payload
    net = FakeNet({"main.py": b"v3"})
    plan = plan_against_local("2026.3.0", root=root, opener=net)
    assert plan.total == 0  # notes.txt is not in MANAGED and not in manifest
