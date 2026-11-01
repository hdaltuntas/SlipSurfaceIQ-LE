"""Delta (file-by-file) self-update for a source-only installation.

See core.py for the implementation used by the Help → Check for Updates dialog.
"""

from slipsurface.patch.core import (
    FileDelta,
    UpdatePlan,
    apply_update,
    diff_manifests,
    fetch_manifest,
    git_blob_sha_bytes,
    git_blob_sha_of,
    install_requirements,
    is_managed,
    plan_against_local,
    plan_update,
    requirements_changed,
    sha256_of,
    write_manifest,
)

__all__ = [
    "FileDelta",
    "UpdatePlan",
    "apply_update",
    "diff_manifests",
    "fetch_manifest",
    "git_blob_sha_bytes",
    "git_blob_sha_of",
    "install_requirements",
    "is_managed",
    "plan_against_local",
    "plan_update",
    "requirements_changed",
    "sha256_of",
    "write_manifest",
]
