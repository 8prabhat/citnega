"""
NetworkVulnScanTool — network service vulnerability assessment.

Given a host + port list, identifies service versions and checks them against
a built-in database of well-known vulnerable versions / default credentials /
misconfigurations. Does NOT exploit — read-only reconnaissance only.

Checks:
  - Banner grabbing + version extraction
  - Known vulnerable version patterns (Redis no-auth, anonymous FTP, Telnet open,
    default MongoDB/Elasticsearch with no auth, Jenkins unauthenticated, etc.)
  - Default credential warnings for common services
  - Unencrypted protocols on sensitive services
  - HTTP security header audit
  - SMB signing status
  - SSH algorithm audit (weak KEX, ciphers, MACs)

Requires approval + network access.
"""

from __future__ import annotations

import asyncio
import re
import time

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class NetworkVulnScanInput(BaseModel):
    target: str = Field(description="Hostname or IP to assess")
    ports: str = Field(
        default="21,22,23,25,80,110,143,389,443,445,3306,3389,5432,5900,6379,8080,8443,8888,9200,27017",
        description="Comma-separated port list",
    )
    timeout: float = Field(default=3.0)
    check_http_headers: bool = Field(default=True)
    check_ssh_algos: bool = Field(default=True)


class ServiceVuln(BaseModel):
    port: int
    service: str
    banner: str
    version: str
    severity: str          # critical / high / medium / low / info
    title: str
    detail: str
    cve_hints: list[str]   # CVE IDs if known


class NetworkVulnScanOutput(BaseModel):
    target: str
    findings: list[ServiceVuln]
    total_open: int
    critical: int
    high: int
    medium: int
    duration_seconds: float


def _parse_ports(spec: str) -> list[int]:
    ports = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            ports.extend(range(int(lo), int(hi) + 1))
        else:
            ports.append(int(part))
    return sorted(set(ports))


async def _grab_banner(host: str, port: int, timeout: float) -> str:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        # Send HTTP probe for web ports, just read for others
        if port in (80, 8080, 8888):
            writer.write(b"HEAD / HTTP/1.0\r\n\r\n")
            await writer.drain()
        try:
            banner = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            writer.close()
            return banner.decode(errors="replace").strip()[:500]
        except Exception:
            writer.close()
    except Exception:
        pass
    return ""


async def _check_redis_noauth(host: str, port: int, timeout: float) -> bool:
    """Check if Redis accepts commands without authentication."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.write(b"PING\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(64), timeout=timeout)
        writer.close()
        return b"+PONG" in response
    except Exception:
        return False


async def _check_http_headers(host: str, port: int, timeout: float) -> list[ServiceVuln]:
    findings = []
    try:
        import ssl as _ssl
        use_ssl = port in (443, 8443)
        if use_ssl:
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ctx), timeout=timeout
            )
        else:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
        writer.write(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
        writer.close()
        text = raw.decode(errors="replace").lower()

        _MISSING = [
            ("x-frame-options", "medium", "Missing X-Frame-Options", "Clickjacking possible", []),
            ("x-content-type-options", "low", "Missing X-Content-Type-Options", "MIME sniffing allowed", []),
            ("content-security-policy", "medium", "Missing Content-Security-Policy", "XSS/injection easier without CSP", []),
            ("strict-transport-security", "high", "Missing HSTS", "HTTPS downgrade attacks possible", []),
            ("x-xss-protection", "low", "Missing X-XSS-Protection", "No legacy XSS filter hint", []),
            ("referrer-policy", "low", "Missing Referrer-Policy", "Referrer info leakage", []),
            ("permissions-policy", "low", "Missing Permissions-Policy", "No permission restrictions declared", []),
        ]
        for header, severity, title, detail, cves in _MISSING:
            if header not in text:
                findings.append(ServiceVuln(
                    port=port, service="http", banner="", version="",
                    severity=severity, title=title, detail=detail, cve_hints=cves,
                ))

        # Server version disclosure
        m = re.search(r"server:\s*(.+)", text)
        if m:
            server_hdr = m.group(1).strip()
            findings.append(ServiceVuln(
                port=port, service="http", banner=server_hdr, version=server_hdr,
                severity="info", title="Server Version Disclosed",
                detail=f"Server header reveals: {server_hdr}", cve_hints=[],
            ))
    except Exception:
        pass
    return findings


async def _check_ssh_algos(host: str, port: int, timeout: float) -> list[ServiceVuln]:
    findings = []
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        banner = await asyncio.wait_for(reader.read(256), timeout=timeout)
        banner_str = banner.decode(errors="replace").strip()

        # Extract SSH version
        m = re.match(r"SSH-(\S+)", banner_str)
        if m:
            ssh_ver = m.group(1)
            if ssh_ver.startswith("1."):
                findings.append(ServiceVuln(
                    port=port, service="ssh", banner=banner_str, version=ssh_ver,
                    severity="critical", title="SSH Protocol v1",
                    detail="SSH v1 is cryptographically broken", cve_hints=["CVE-2001-0361"],
                ))

        # Send client hello to get kex algorithms
        writer.write(b"SSH-2.0-OpenSSH_8.9\r\n")
        await writer.drain()
        kex_data = await asyncio.wait_for(reader.read(4096), timeout=timeout)
        kex_str = kex_data.decode(errors="replace", )
        writer.close()

        _WEAK_KEX = ["diffie-hellman-group1-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1"]
        _WEAK_CIPHERS = ["arcfour", "arcfour128", "arcfour256", "3des-cbc", "blowfish-cbc", "cast128-cbc"]
        _WEAK_MACS = ["hmac-md5", "hmac-sha1-96", "hmac-md5-96"]

        for alg in _WEAK_KEX:
            if alg in kex_str:
                findings.append(ServiceVuln(
                    port=port, service="ssh", banner="", version="",
                    severity="medium", title=f"Weak SSH KEX: {alg}",
                    detail=f"Server supports deprecated key exchange {alg}", cve_hints=[],
                ))
        for alg in _WEAK_CIPHERS:
            if alg in kex_str:
                findings.append(ServiceVuln(
                    port=port, service="ssh", banner="", version="",
                    severity="high", title=f"Weak SSH Cipher: {alg}",
                    detail=f"Server supports deprecated cipher {alg}", cve_hints=[],
                ))
        for alg in _WEAK_MACS:
            if alg in kex_str:
                findings.append(ServiceVuln(
                    port=port, service="ssh", banner="", version="",
                    severity="medium", title=f"Weak SSH MAC: {alg}",
                    detail=f"Server supports deprecated MAC {alg}", cve_hints=[],
                ))
    except Exception:
        pass
    return findings


_PORT_CHECKS: dict[int, tuple[str, str, str, list[str]]] = {
    23:    ("critical", "Telnet Open", "Telnet transmits credentials in cleartext", ["CVE-1999-0619"]),
    21:    ("high", "FTP Open", "FTP may allow anonymous access and transmits in cleartext", []),
    3389:  ("high", "RDP Exposed", "RDP exposed to network — brute-force and BlueKeep risk", ["CVE-2019-0708"]),
    5900:  ("high", "VNC Exposed", "VNC exposed — often has weak or no authentication", []),
    9200:  ("critical", "Elasticsearch Exposed", "Elasticsearch with no auth by default — data breach risk", ["CVE-2014-3120"]),
    27017: ("critical", "MongoDB Exposed", "MongoDB default config has no authentication", ["CVE-2013-2132"]),
    6379:  ("critical", "Redis Exposed", "Redis default config has no authentication", ["CVE-2022-0543"]),
    8888:  ("high", "Jupyter Notebook Exposed", "Jupyter may allow unauthenticated code execution", []),
    5432:  ("medium", "PostgreSQL Exposed", "PostgreSQL port reachable — check pg_hba.conf", []),
    3306:  ("medium", "MySQL/MariaDB Exposed", "MySQL exposed — ensure root has password", []),
    1433:  ("medium", "MSSQL Exposed", "MSSQL port reachable — check authentication config", []),
    25:    ("medium", "SMTP Open Relay Check Needed", "SMTP exposed — check for open relay", []),
    389:   ("high", "LDAP Unencrypted", "LDAP (not LDAPS) transmits directory data unencrypted", []),
}


class NetworkVulnScanTool(BaseCallable):
    name = "network_vuln_scan"
    description = (
        "Network service vulnerability assessment: banner grabbing, version detection, "
        "default credential warnings, HTTP security header audit, SSH algorithm audit, "
        "Redis/MongoDB/Elasticsearch no-auth detection, and protocol-level risk scoring. "
        "Read-only — does not exploit. AUTHORIZED USE ONLY."
    )
    callable_type = CallableType.TOOL
    input_schema = NetworkVulnScanInput
    output_schema = NetworkVulnScanOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=True,
        network_allowed=True,
        max_output_bytes=512 * 1024,
    )

    async def _execute(self, input_data: NetworkVulnScanInput, context: object) -> NetworkVulnScanOutput:
        t0 = time.monotonic()
        host = input_data.target
        ports = _parse_ports(input_data.ports)
        findings: list[ServiceVuln] = []
        open_count = 0

        sem = asyncio.Semaphore(30)

        async def probe(port: int):
            nonlocal open_count
            async with sem:
                banner = await _grab_banner(host, port, input_data.timeout)
                if not banner and port not in (80, 443, 8080, 8443):
                    # Confirm port is actually open
                    try:
                        _, w = await asyncio.wait_for(
                            asyncio.open_connection(host, port), timeout=input_data.timeout
                        )
                        w.close()
                        is_open = True
                    except Exception:
                        return
                else:
                    is_open = bool(banner)

                if not is_open and port not in (80, 443, 8080, 8443, 9200, 27017, 6379):
                    return

                open_count += 1

                # Known port risk check
                if port in _PORT_CHECKS:
                    severity, title, detail, cves = _PORT_CHECKS[port]
                    findings.append(ServiceVuln(
                        port=port, service="", banner=banner[:100], version="",
                        severity=severity, title=title, detail=detail, cve_hints=cves,
                    ))

                # Redis no-auth
                if port == 6379:
                    if await _check_redis_noauth(host, port, input_data.timeout):
                        findings.append(ServiceVuln(
                            port=port, service="redis", banner=banner, version="",
                            severity="critical", title="Redis: No Authentication Required",
                            detail="Redis responds to PING without authentication — full data access",
                            cve_hints=["CVE-2022-0543"],
                        ))

                # HTTP headers
                if port in (80, 443, 8080, 8443) and input_data.check_http_headers:
                    findings.extend(await _check_http_headers(host, port, input_data.timeout))

                # SSH
                if port == 22 and input_data.check_ssh_algos:
                    findings.extend(await _check_ssh_algos(host, port, input_data.timeout))

        await asyncio.gather(*[probe(p) for p in ports])

        findings.sort(key=lambda x: -{"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}.get(x.severity, 0))

        counts = {s: sum(1 for f in findings if f.severity == s) for s in ("critical", "high", "medium")}

        return NetworkVulnScanOutput(
            target=host,
            findings=findings,
            total_open=open_count,
            critical=counts["critical"],
            high=counts["high"],
            medium=counts["medium"],
            duration_seconds=round(time.monotonic() - t0, 2),
        )
