"""Delta (changed-files-only) updater tests: manifest diff, apply, restore."""

import hashlib
import json

import pytest

from slipsurface.patch import (
    FileDelta,
    UpdatePlan,
    apply_update,
    diff_manifests,
    git_blob_sha_bytes,
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
        ("tests/test_patch.py", False),  # the test suite is not shipped in updates
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
    backup = root / ".update-backup" / "2026.2.0-to-2026.3.0"
    assert (backup / "main.py").read_text() == "old"
    assert (backup / "slipsurface" / "drop.py").read_text() == "drop"
    assert "1 changed" in summary
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


def test_git_tree_fallback_when_manifest_asset_returns_404(tmp_path):
    """When a release has no manifest.json asset (HTTP 404), fall back to Git Trees API."""
    import urllib.error

    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_bytes(b"old\r\nline\r\n")
    (root / "slipsurface" / "keep.py").write_bytes(b"same\r\n")
    (root / "slipsurface" / "drop.py").write_bytes(b"drop\n")

    remote_files = {
        "main.py": b"new\nline\n",
        "slipsurface/keep.py": b"same\n",
        "slipsurface/added.py": b"added\n",
    }

    def tree_opener(request, timeout):
        url = request.full_url
        if url.endswith("manifest.json"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if "/git/trees/v2026.3.3?recursive=1" in url:
            tree = [
                {"path": k, "mode": "100644", "type": "blob", "sha": git_blob_sha_bytes(v)}
                for k, v in remote_files.items()
            ] + [{"path": ".git/config", "mode": "100644", "type": "blob", "sha": "0" * 40}]
            return FakeResponse(json.dumps({"sha": "abc", "tree": tree}).encode("utf-8"))
        if "/v2026.3.3/" in url:
            rel = url.split("/v2026.3.3/", 1)[1]
            if rel in remote_files:
                return FakeResponse(remote_files[rel])
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    plan = plan_against_local("2026.3.3", root=root, opener=tree_opener)
    # keep.py with CRLF matches LF git blob SHA-1 and is not re-downloaded
    assert [d.relpath for d in plan.changed] == ["main.py"]
    assert [d.relpath for d in plan.new] == ["slipsurface/added.py"]
    assert [d.relpath for d in plan.removed] == ["slipsurface/drop.py"]

    summary = apply_update(plan, "2026.3.3", root=root, opener=tree_opener)
    assert (root / "main.py").read_bytes() == b"new\nline\n"
    assert (root / "slipsurface" / "keep.py").read_bytes() == b"same\r\n"
    assert (root / "slipsurface" / "added.py").read_bytes() == b"added\n"
    assert not (root / "slipsurface" / "drop.py").exists()
    assert "2026.3.3" in summary


def test_bare_version_tag_fallback_without_v_prefix(tmp_path):
    """Releases tagged without a leading 'v' (e.g. 2026.3.3) also resolve."""
    import urllib.error

    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_bytes(b"old\n")

    def bare_tag_opener(request, timeout):
        url = request.full_url
        if "/v2026.3.3" in url or url.endswith("manifest.json"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if "/git/trees/2026.3.3?recursive=1" in url:
            tree = [{"path": "main.py", "type": "blob", "sha": git_blob_sha_bytes(b"updated\n")}]
            return FakeResponse(json.dumps({"tree": tree}).encode("utf-8"))
        if url.endswith("/2026.3.3/main.py"):
            return FakeResponse(b"updated\n")
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    plan = plan_against_local("2026.3.3", root=root, opener=bare_tag_opener)
    assert [d.relpath for d in plan.changed] == ["main.py"]
    apply_update(plan, "2026.3.3", root=root, opener=bare_tag_opener)
    assert (root / "main.py").read_bytes() == b"updated\n"


# ------------------------------------------------------------- safety
@pytest.mark.parametrize(
    "rel",
    [
        "../evil.py",
        "slipsurface/../../evil.py",
        "/etc/passwd",
        "C:/x.py",
        "slipsurface\\x.py",
        "slipsurface//x.py",
        "./main.py",
        "",
    ],
)
def test_unsafe_paths_are_never_managed(rel):
    assert not is_managed(rel)


def test_manifest_with_unsafe_path_is_ignored(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "main.py").write_text("v3")
    net = FakeNet({"main.py": b"v3", "../outside.py": b"x", "slipsurface/../../o.py": b"x"})
    plan = plan_against_local("2026.3.0", root=root, opener=net)
    assert plan.total == 0
    assert not (tmp_path / "outside.py").exists()


def test_apply_refuses_unsafe_plan(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    plan = UpdatePlan("1", "2", new=[FileDelta("../evil.py", "new", new_hash="x")])
    with pytest.raises(UpdateCheckError):
        apply_update(plan, "2026.3.0", root=root, opener=FakeNet({}))
    assert not (tmp_path / "evil.py").exists()


def test_user_files_in_examples_are_kept(tmp_path):
    """A project the user saved next to the examples is not deleted by an update."""
    root = tmp_path / "app"
    (root / "examples").mkdir(parents=True)
    (root / "main.py").write_text("v3")
    (root / "examples" / "my_project.slp.json").write_text("{}")
    net = FakeNet({"main.py": b"v3"})
    plan = plan_against_local("2026.3.0", root=root, opener=net)
    assert plan.total == 0


def test_failed_download_leaves_installation_unchanged(tmp_path):
    """Nothing is replaced or removed unless every download verified."""
    root = tmp_path / "app"
    (root / "slipsurface").mkdir(parents=True)
    (root / "main.py").write_text("old")
    (root / "slipsurface" / "drop.py").write_text("drop")
    net = FakeNet({"main.py": b"new", "slipsurface/added.py": b"tampered"})
    plan = UpdatePlan(
        "2026.2.0",
        "2026.3.0",
        changed=[FileDelta("main.py", "changed", new_hash=sha256_bytes(b"new"))],
        new=[FileDelta("slipsurface/added.py", "new", new_hash=sha256_bytes(b"added"))],
        removed=[FileDelta("slipsurface/drop.py", "removed")],
    )
    with pytest.raises(UpdateCheckError, match="hash mismatch"):
        apply_update(plan, "2026.3.0", root=root, opener=net)
    assert (root / "main.py").read_text() == "old"
    assert (root / "slipsurface" / "drop.py").read_text() == "drop"
    assert not (root / "slipsurface" / "added.py").exists()
    assert not (root / ".update-backup").exists()


def test_each_update_gets_its_own_backup(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    for old, new in (("v1", b"v2"), ("v2", b"v3")):
        (root / "main.py").write_text(old)
        plan = UpdatePlan(
            "2026.2.0",
            "2026.3.0",
            changed=[FileDelta("main.py", "changed", new_hash=sha256_bytes(new))],
        )
        apply_update(plan, "2026.3.0", root=root, opener=FakeNet({"main.py": new}))
    backups = sorted(p.read_text() for p in (root / ".update-backup").rglob("main.py"))
    assert backups == ["v1", "v2"]


# -------------------------------------------------------- signed manifests
SEED = bytes(range(32))


class SignedNet(FakeNet):
    """Serves manifest.json plus a manifest.json.sig made with ``seed``."""

    def __init__(self, files, seed=SEED, tamper=False, unsigned=False):
        super().__init__(files)
        self.seed, self.tamper, self.unsigned = seed, tamper, unsigned

    def _serve(self, url, rel):
        from slipsurface.patch import signing

        if url.endswith("manifest.json.sig"):
            if self.unsigned:
                raise UpdateCheckError("HTTP 404 manifest.json.sig")
            manifest = super()._serve(url[: -len(".sig")], rel)
            return signing.sign(self.seed, manifest).hex().encode()
        payload = super()._serve(url, rel)
        if self.tamper and url.endswith("manifest.json"):
            payload = payload.replace(b"2026.3.0", b"2026.3.9")
        return payload


@pytest.fixture
def trusted_key(monkeypatch):
    from slipsurface.patch import signing

    monkeypatch.setattr(signing, "TRUSTED_PUBLIC_KEYS", (signing.public_key(SEED).hex(),))


def test_ed25519_rfc8032_vector():
    from slipsurface.patch import signing

    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    public = signing.public_key(seed)
    assert public.hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    signature = signing.sign(seed, b"")
    assert signature.hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    assert signing.verify(public, b"", signature)
    assert not signing.verify(public, b"x", signature)
    assert not signing.verify(public, b"", signature[:-1] + b"\x00")


def test_signed_manifest_is_accepted(tmp_path, trusted_key):
    root = tmp_path / "app"
    root.mkdir()
    net = SignedNet({"main.py": b"new"})
    plan = plan_against_local("2026.3.0", root=root, opener=net)
    apply_update(plan, "2026.3.0", root=root, opener=net)
    assert (root / "main.py").read_bytes() == b"new"


@pytest.mark.parametrize(
    "net",
    [
        SignedNet({"main.py": b"new"}, tamper=True),
        SignedNet({"main.py": b"new"}, unsigned=True),
        SignedNet({"main.py": b"new"}, seed=bytes(32)),  # signed by an unknown key
    ],
    ids=["tampered", "unsigned", "wrong-key"],
)
def test_unverified_manifest_is_refused(tmp_path, trusted_key, net):
    root = tmp_path / "app"
    root.mkdir()
    with pytest.raises(UpdateCheckError):
        plan_against_local("2026.3.0", root=root, opener=net)
    # no fall-back to the unsigned Git tree listing
    assert not any("/git/trees/" in url for url in net.fetched)
    assert not (root / "main.py").exists()


def test_signing_off_without_trusted_keys(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    net = SignedNet({"main.py": b"new"}, unsigned=True)
    plan = plan_against_local("2026.3.0", root=root, opener=net)
    assert [d.relpath for d in plan.new] == ["main.py"]
