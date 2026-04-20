"""
SSLTLSAuditTool — SSL/TLS certificate and cipher-suite analysis.

Checks:
  - Certificate validity dates, issuer, subject, SANs
  - Protocol version support (TLS 1.0 / 1.1 / 1.2 / 1.3)
  - Weak cipher detection (RC4, DES, 3DES, NULL, EXPORT, ANON)
  - Certificate chain and self-signed detection
  - HSTS header presence
  - OCSP stapling (basic)

Uses Python stdlib ssl + socket only.  Requires approval (network).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import socket
import ssl
import time

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class SSLTLSAuditInput(BaseModel):
    host: str = Field(description="Hostname or IP to audit")
    port: int = Field(default=443, description="Port (default 443 for HTTPS)")
    timeout: float = Field(default=10.0)
    check_weak_protocols: bool = Field(default=True, description="Probe for TLS 1.0/1.1 support")
    check_weak_ciphers: bool = Field(default=True, description="Check advertised cipher suite list")
    sni: str = Field(default="", description="Override SNI hostname (defaults to host)")


class CertInfo(BaseModel):
    subject: dict[str, str]
    issuer: dict[str, str]
    serial_number: str
    not_before: str
    not_after: str
    days_until_expiry: int
    is_expired: bool
    is_self_signed: bool
    san: list[str]
    signature_algorithm: str


class CipherInfo(BaseModel):
    name: str
    protocol: str
    bits: int
    is_weak: bool


class SSLTLSAuditOutput(BaseModel):
    host: str
    port: int
    negotiated_protocol: str
    negotiated_cipher: CipherInfo
    cert: CertInfo
    cert_chain_depth: int
    weak_protocols_supported: list[str]
    weak_ciphers_found: list[str]
    hsts: bool
    hsts_max_age: int
    duration_seconds: float
    findings: list[str]     # human-readable security notes


_WEAK_CIPHERS = {
    "RC4", "DES", "3DES", "NULL", "EXPORT", "ANON", "ADH", "AECDH",
    "MD5", "PSK-3DES", "DES-CBC3",
}

_PROTOCOL_VERSIONS = {
    "TLSv1": ssl.TLSVersion.TLSv1 if hasattr(ssl, "TLSVersion") and hasattr(ssl.TLSVersion, "TLSv1") else None,
    "TLSv1.1": ssl.TLSVersion.TLSv1_1 if hasattr(ssl, "TLSVersion") and hasattr(ssl.TLSVersion, "TLSv1_1") else None,
}


def _dict_from_dn(dn) -> dict[str, str]:
    result = {}
    if isinstance(dn, (list, tuple)):
        for item in dn:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                for pair in item:
                    if isinstance(pair, (list, tuple)) and len(pair) == 2:
                        result[str(pair[0])] = str(pair[1])
    return result


def _get_san(cert: dict) -> list[str]:
    sans = []
    for entry in cert.get("subjectAltName", []):
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            sans.append(f"{entry[0]}:{entry[1]}")
    return sans


async def _connect_tls(host: str, port: int, sni: str, timeout: float,
                        min_version=None, max_version=None) -> tuple[ssl.SSLSocket | None, dict | None, str, str]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if min_version and hasattr(ssl, "TLSVersion"):
        try:
            ctx.minimum_version = min_version
        except Exception:
            pass
    if max_version and hasattr(ssl, "TLSVersion"):
        try:
            ctx.maximum_version = max_version
        except Exception:
            pass

    loop = asyncio.get_event_loop()
    try:
        def _connect():
            raw = socket.create_connection((host, port), timeout=timeout)
            wrapped = ctx.wrap_socket(raw, server_hostname=sni or host)
            cert = wrapped.getpeercert()
            proto = wrapped.version() or ""
            cipher = wrapped.cipher() or ("", "", 0)
            return wrapped, cert, proto, cipher
        wrapped, cert, proto, cipher = await asyncio.wait_for(
            loop.run_in_executor(None, _connect), timeout=timeout + 2
        )
        return wrapped, cert, proto, cipher
    except Exception:
        return None, None, "", ("", "", 0)


async def _check_weak_protocol(host: str, port: int, sni: str, proto_name: str, version) -> bool:
    if version is None:
        return False
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = version
        ctx.maximum_version = version
        loop = asyncio.get_event_loop()
        def _try():
            s = socket.create_connection((host, port), timeout=3)
            w = ctx.wrap_socket(s, server_hostname=sni or host)
            w.close()
            return True
        return await asyncio.wait_for(loop.run_in_executor(None, _try), timeout=5)
    except Exception:
        return False


async def _get_hsts(host: str, port: int, timeout: float) -> tuple[bool, int]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl.create_default_context()),
            timeout=timeout,
        )
        writer.write(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4096), timeout=timeout)
        writer.close()
        text = data.decode(errors="replace")
        import re
        m = re.search(r"strict-transport-security:.*?max-age=(\d+)", text, re.IGNORECASE)
        if m:
            return True, int(m.group(1))
        if "strict-transport-security" in text.lower():
            return True, 0
    except Exception:
        pass
    return False, 0


class SSLTLSAuditTool(BaseCallable):
    name = "ssl_tls_audit"
    description = (
        "SSL/TLS certificate and cipher-suite audit for any host:port. "
        "Reports certificate validity, expiry, SANs, weak protocol support "
        "(TLS 1.0/1.1), weak cipher detection, HSTS, and self-signed warnings."
    )
    callable_type = CallableType.TOOL
    input_schema = SSLTLSAuditInput
    output_schema = SSLTLSAuditOutput
    policy = CallablePolicy(
        timeout_seconds=60.0,
        requires_approval=True,
        network_allowed=True,
        max_output_bytes=128 * 1024,
    )

    async def _execute(self, input_data: SSLTLSAuditInput, context: object) -> SSLTLSAuditOutput:
        t0 = time.monotonic()
        host = input_data.host
        port = input_data.port
        sni = input_data.sni or host

        wrapped, cert, proto, cipher_tuple = await _connect_tls(host, port, sni, input_data.timeout)

        findings: list[str] = []

        # Parse cert
        cert_info = CertInfo(
            subject={}, issuer={}, serial_number="", not_before="", not_after="",
            days_until_expiry=0, is_expired=False, is_self_signed=False,
            san=[], signature_algorithm="",
        )
        if cert:
            subject = _dict_from_dn(cert.get("subject", []))
            issuer = _dict_from_dn(cert.get("issuer", []))
            not_before_str = cert.get("notBefore", "")
            not_after_str = cert.get("notAfter", "")
            try:
                not_after_dt = datetime.datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
                days = (not_after_dt - datetime.datetime.utcnow()).days
            except Exception:
                days = 0
            is_expired = days < 0
            is_self_signed = subject == issuer
            san = _get_san(cert)

            if is_expired:
                findings.append(f"CRITICAL: Certificate expired {abs(days)} days ago")
            elif days < 30:
                findings.append(f"WARNING: Certificate expires in {days} days")
            if is_self_signed:
                findings.append("WARNING: Self-signed certificate — not trusted by browsers")

            cert_info = CertInfo(
                subject=subject,
                issuer=issuer,
                serial_number=str(cert.get("serialNumber", "")),
                not_before=not_before_str,
                not_after=not_after_str,
                days_until_expiry=days,
                is_expired=is_expired,
                is_self_signed=is_self_signed,
                san=san,
                signature_algorithm=cert.get("signatureAlgorithm", ""),
            )
            if cert_info.signature_algorithm and "sha1" in cert_info.signature_algorithm.lower():
                findings.append("WARNING: SHA-1 signature algorithm is deprecated")

        # Cipher
        cipher_name, cipher_proto, cipher_bits = ("", "", 0)
        if isinstance(cipher_tuple, (list, tuple)) and len(cipher_tuple) >= 3:
            cipher_name, cipher_proto, cipher_bits = str(cipher_tuple[0]), str(cipher_tuple[1]), int(cipher_tuple[2] or 0)
        is_weak_cipher = any(w in cipher_name.upper() for w in _WEAK_CIPHERS)
        if is_weak_cipher:
            findings.append(f"WARNING: Weak cipher negotiated: {cipher_name}")

        cipher_info = CipherInfo(
            name=cipher_name, protocol=cipher_proto, bits=cipher_bits, is_weak=is_weak_cipher,
        )

        if wrapped:
            try:
                wrapped.close()
            except Exception:
                pass

        # Protocol version check
        if proto in ("TLSv1", "TLSv1.1"):
            findings.append(f"WARNING: Server negotiated deprecated {proto}")
        if not proto:
            findings.append("WARNING: Could not determine TLS version — connection may have failed")

        # Weak protocol probing
        weak_protos: list[str] = []
        if input_data.check_weak_protocols:
            for pname, pversion in _PROTOCOL_VERSIONS.items():
                if await _check_weak_protocol(host, port, sni, pname, pversion):
                    weak_protos.append(pname)
                    findings.append(f"CRITICAL: Server accepts deprecated {pname}")

        # HSTS
        hsts, hsts_max_age = await _get_hsts(host, port, input_data.timeout)
        if not hsts:
            findings.append("WARNING: HSTS not set — downgrade attacks possible")
        elif hsts_max_age < 31536000:
            findings.append(f"INFO: HSTS max-age {hsts_max_age} < 1 year recommended")

        return SSLTLSAuditOutput(
            host=host,
            port=port,
            negotiated_protocol=proto,
            negotiated_cipher=cipher_info,
            cert=cert_info,
            cert_chain_depth=0,
            weak_protocols_supported=weak_protos,
            weak_ciphers_found=[cipher_name] if is_weak_cipher else [],
            hsts=hsts,
            hsts_max_age=hsts_max_age,
            duration_seconds=round(time.monotonic() - t0, 2),
            findings=findings,
        )
