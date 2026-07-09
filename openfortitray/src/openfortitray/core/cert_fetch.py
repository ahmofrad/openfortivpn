"""TLS certificate fetch for TOFU pinning (AUTH.md §6).

Opens a raw TLS connection to host:port with verification disabled
(inspection only -- never used for the actual VPN connection),
reads the peer certificate, and computes its SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import logging
import socket
import ssl
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CertInfo:
    sha256_digest: str         # colon-separated hex, e.g. "e4:6d:4a:ff:..."
    sha256_digest_raw: str     # continuous hex, e.g. "e46d4aff..."
    subject: str
    issuer: str
    not_before: str
    not_after: str


def fetch_certificate(host: str, port: int = 443, timeout: float = 10.0) -> CertInfo:
    """Connect to host:port, read the TLS certificate, return its info.

    Verification is intentionally disabled for this inspection step only
    (AUTH.md §6). The caller must display a warning and ask the user to
    verify the fingerprint through a separate channel.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            der_cert = ssock.getpeercert(binary_form=True)
            cert_dict = ssock.getpeercert()

    if not der_cert:
        raise RuntimeError("Server did not present a certificate.")

    digest_raw = hashlib.sha256(der_cert).hexdigest()
    digest_colon = ":".join(digest_raw[i:i + 2] for i in range(0, len(digest_raw), 2))

    subject = _format_name(cert_dict.get("subject", {}))
    issuer = _format_name(cert_dict.get("issuer", {}))

    not_before = cert_dict.get("notBefore", "unknown")
    not_after = cert_dict.get("notAfter", "unknown")

    return CertInfo(
        sha256_digest=digest_colon,
        sha256_digest_raw=digest_raw,
        subject=subject,
        issuer=issuer,
        not_before=not_before,
        not_after=not_after,
    )


def _format_name(name_field: dict | tuple) -> str:
    """Format an ssl cert subject/issuer field into a readable string."""
    if isinstance(name_field, str):
        return name_field

    parts: list[str] = []
    if isinstance(name_field, dict):
        for key, values in name_field.items():
            if isinstance(values, list):
                for v in values:
                    if isinstance(v, tuple):
                        parts.append(f"{v[0]}={v[1]}")
                    else:
                        parts.append(f"{key}={v}")
            elif isinstance(values, tuple):
                parts.append(f"{key}={values[0]}")
    elif isinstance(name_field, (list, tuple)):
        for item in name_field:
            if isinstance(item, tuple) and len(item) == 2:
                parts.append(f"{item[0]}={item[1]}")

    return ", ".join(parts) if parts else "unknown"
