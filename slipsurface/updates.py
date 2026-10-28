"""Check GitHub for a newer published release (no Qt; used by the UI).

Only the public "latest release" endpoint is queried: drafts and
pre-releases are never offered. Nothing is downloaded or installed;
users are directed to a source-code release, then run main.py.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from slipsurface import __version__

REPOSITORY = "hdaltuntas/SlipSurfaceIQ-LE"
LATEST_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"

# Certificate bundles of common Linux distributions and macOS.
CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",  # Debian, Ubuntu, Arch
    "/etc/pki/tls/certs/ca-bundle.crt",  # Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",  # openSUSE
    "/etc/ssl/cert.pem",  # macOS, Alpine
)

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class UpdateCheckError(RuntimeError):
    """The release information could not be retrieved or understood."""


@dataclass
class ReleaseInfo:
    version: str  # e.g. "2026.1.5"
    url: str  # release page
    notes: str = ""
    published: str = ""  # ISO date, e.g. "2026-10-27"


def parse_version(text: str) -> tuple[int, int, int] | None:
    """(year, minor, patch) for "2026.1.5" or "v2026.1.5"; None otherwise."""
    m = _VERSION.match(text.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, cur = parse_version(candidate), parse_version(current)
    return new is not None and cur is not None and new > cur


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not ctx.cert_store_stats()["x509_ca"] and not os.environ.get("SSL_CERT_FILE"):
        for path in CA_BUNDLES:
            if os.path.isfile(path):
                ctx.load_verify_locations(cafile=path)
                break
    return ctx


def _default_open(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def fetch_latest(
    timeout: float = 8.0,
    opener: Callable[[urllib.request.Request, float], object] | None = None,
) -> ReleaseInfo:
    """The latest published release. Raises UpdateCheckError."""
    request = urllib.request.Request(
        LATEST_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SlipSurfaceIQ-LE/{__version__}",
        },
    )
    try:
        with (opener or _default_open)(request, timeout) as response:  # type: ignore[attr-defined]
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateCheckError("no published release") from None
        raise UpdateCheckError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateCheckError(str(reason)) from None
    except (ValueError, UnicodeDecodeError):
        raise UpdateCheckError("invalid response") from None
    if not isinstance(data, dict):
        raise UpdateCheckError("invalid response")
    tag = str(data.get("tag_name", ""))
    if parse_version(tag) is None:
        raise UpdateCheckError(f"unrecognised release tag {tag!r}")
    url = str(data.get("html_url") or "")
    if not url.startswith(f"https://github.com/{REPOSITORY}/"):
        url = RELEASES_PAGE  # only ever open the project's own release page
    return ReleaseInfo(
        version=tag.lstrip("v"),
        url=url,
        notes=str(data.get("body") or ""),
        published=str(data.get("published_at") or "")[:10],
    )
