"""Delta (file-by-file) self-update: ``python -m slipsurface.patch``.

See core.py for the implementation and the CLI in __main__.py.
"""

from slipsurface.patch.core import (
    FileDelta,
    UpdatePlan,
    apply_update,
    diff_manifests,
    fetch_manifest,
    is_managed,
    plan_against_local,
    plan_update,
    sha256_of,
    write_manifest,
)

__all__ = [
    "FileDelta",
    "UpdatePlan",
    "apply_update",
    "diff_manifests",
    "fetch_manifest",
    "is_managed",
    "plan_against_local",
    "plan_update",
    "sha256_of",
    "write_manifest",
]
