"""Ed25519 signatures for the release manifest (pure Python, RFC 8032).

The release workflow signs ``manifest.json`` with a private key kept as a
GitHub secret and publishes the signature as ``manifest.json.sig`` (hex).
When :data:`TRUSTED_PUBLIC_KEYS` lists at least one key, the updater only
installs from a manifest whose signature verifies against one of them, so a
modified manifest or file cannot be installed even if the download host is
compromised. With no key configured, updates rely on HTTPS and the per-file
hashes alone, as before.

Command line (maintainers only)::

    python -m slipsurface.patch.signing genkey            # new key pair
    python -m slipsurface.patch.signing sign manifest.json  # needs MANIFEST_SIGNING_KEY
    python -m slipsurface.patch.signing verify manifest.json manifest.json.sig

This is a straightforward implementation of the RFC 8032 reference code. It
is not constant-time, which is irrelevant for verification and acceptable for
signing a public manifest in CI.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
from pathlib import Path

# Hex-encoded Ed25519 public keys whose signatures the updater accepts.
# Empty: signature checking is off. Add the key printed by ``genkey``.
TRUSTED_PUBLIC_KEYS: tuple[str, ...] = (
    "f1d1ef21730d3d5f099f4054e4738b611c9f722ef138dd8e67ec54793e9016d4",
)

SIGNATURE_SUFFIX = ".sig"
SECRET_ENV = "MANIFEST_SIGNING_KEY"

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)  # sqrt(-1)


class SignatureError(ValueError):
    """A signature or key is malformed or does not verify."""


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _sha512_int(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little")


# Points in extended coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z, xy = T/Z.
def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s: int, p):
    q = (0, 1, 1, 0)  # neutral element
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(p, q) -> bool:
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
assert _GX is not None
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(p) -> bytes:
    zinv = pow(p[2], _P - 2, _P)
    x, y = p[0] * zinv % _P, p[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        raise SignatureError("Ed25519 points are 32 bytes")
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        raise SignatureError("invalid Ed25519 point")
    return (x, y, 1, x * y % _P)


def _expand(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise SignatureError("Ed25519 private keys are 32 bytes")
    h = _sha512(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _compress(_mul(a, _G))


def sign(seed: bytes, message: bytes) -> bytes:
    a, prefix = _expand(seed)
    pub = _compress(_mul(a, _G))
    r = _sha512_int(prefix + message) % _L
    big_r = _compress(_mul(r, _G))
    h = _sha512_int(big_r + pub + message) % _L
    s = (r + h * a) % _L
    return big_r + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """True when ``signature`` is a valid Ed25519 signature of ``message``."""
    try:
        if len(public) != 32 or len(signature) != 64:
            return False
        a = _decompress(public)
        big_r = _decompress(signature[:32])
    except SignatureError:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = _sha512_int(signature[:32] + public + message) % _L
    return _equal(_mul(s, _G), _add(big_r, _mul(h, a)))


def _hex_bytes(text: str, size: int, what: str) -> bytes:
    try:
        data = bytes.fromhex(text.strip())
    except ValueError as exc:
        raise SignatureError(f"{what} is not hexadecimal") from exc
    if len(data) != size:
        raise SignatureError(f"{what} must be {size} bytes ({2 * size} hex digits)")
    return data


def signature_required(keys: tuple[str, ...] | None = None) -> bool:
    return bool(TRUSTED_PUBLIC_KEYS if keys is None else keys)


def verify_manifest(
    manifest: bytes, signature_hex: str, keys: tuple[str, ...] | None = None
) -> bool:
    """Whether the manifest bytes are signed by one of the trusted keys."""
    keys = TRUSTED_PUBLIC_KEYS if keys is None else keys
    try:
        signature = _hex_bytes(signature_hex, 64, "signature")
    except SignatureError:
        return False
    return any(verify(_hex_bytes(k, 32, "public key"), manifest, signature) for k in keys)


def _main(argv: list[str]) -> int:
    if argv[:1] == ["genkey"]:
        seed = secrets.token_bytes(32)
        print(f"Private key (store ONLY as the GitHub secret {SECRET_ENV}):")
        print(seed.hex())
        print("Public key (add to TRUSTED_PUBLIC_KEYS in slipsurface/patch/signing.py):")
        print(public_key(seed).hex())
        return 0
    if len(argv) == 2 and argv[0] == "sign":
        key = os.environ.get(SECRET_ENV, "")
        if not key:
            print(f"{SECRET_ENV} is not set; manifest left unsigned.", file=sys.stderr)
            return 0
        path = Path(argv[1])
        signature = sign(_hex_bytes(key, 32, SECRET_ENV), path.read_bytes())
        Path(str(path) + SIGNATURE_SUFFIX).write_text(signature.hex() + "\n", encoding="ascii")
        print(f"signed {path} with key {public_key(_hex_bytes(key, 32, SECRET_ENV)).hex()}")
        return 0
    if len(argv) in (3, 4) and argv[0] == "verify":
        keys = (argv[3],) if len(argv) == 4 else None
        sig = Path(argv[2]).read_text(encoding="ascii")
        ok = verify_manifest(Path(argv[1]).read_bytes(), sig, keys)
        print("signature OK" if ok else "signature INVALID")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
