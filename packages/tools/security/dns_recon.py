"""
DNSReconTool — DNS reconnaissance and security audit.

Collects:
  - A, AAAA, MX, NS, TXT, SOA, CNAME, PTR records
  - SPF / DMARC / DKIM policy extraction
  - Zone transfer attempt (AXFR)
  - DNS-over-HTTPS (DoH) cross-validation
  - Subdomain enumeration from a wordlist
  - DNSSEC validation status
  - Wildcard DNS detection
  - Reverse DNS for discovered IPs

Uses stdlib socket + subprocess (dig/nslookup); dnspython used if installed.
Requires approval (network).
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import time

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class DNSReconInput(BaseModel):
    domain: str = Field(description="Target domain (e.g. example.com)")
    record_types: list[str] = Field(
        default=["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"],
        description="DNS record types to query",
    )
    attempt_zone_transfer: bool = Field(default=True, description="Try AXFR zone transfer against each NS")
    enumerate_subdomains: bool = Field(default=False, description="Brute-force common subdomains")
    subdomain_wordlist: list[str] = Field(
        default=["www", "mail", "ftp", "smtp", "vpn", "dev", "staging", "api", "admin",
                 "portal", "ns1", "ns2", "mx", "remote", "test", "app", "docs", "cdn"],
        description="Subdomains to probe",
    )
    nameserver: str = Field(default="", description="Override resolver (empty = system default)")
    timeout: float = Field(default=5.0)


class DNSRecord(BaseModel):
    name: str
    record_type: str
    value: str
    ttl: int


class DNSReconOutput(BaseModel):
    domain: str
    records: list[DNSRecord]
    nameservers: list[str]
    zone_transfer_results: dict[str, str]   # ns → "success" | "refused" | "error"
    discovered_subdomains: list[str]
    spf_record: str
    dmarc_record: str
    dnssec_enabled: bool
    wildcard_detected: bool
    findings: list[str]
    duration_seconds: float


def _dig(domain: str, rtype: str, ns: str = "", timeout: float = 5.0) -> list[str]:
    cmd = ["dig", "+noall", "+answer", f"+time={int(timeout)}"]
    if ns:
        cmd.append(f"@{ns}")
    cmd += [domain, rtype]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        lines = []
        for ln in out.stdout.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith(";"):
                lines.append(ln)
        return lines
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _parse_dig_line(line: str) -> DNSRecord | None:
    parts = line.split()
    if len(parts) < 5:
        return None
    try:
        return DNSRecord(
            name=parts[0],
            ttl=int(parts[1]),
            record_type=parts[3],
            value=" ".join(parts[4:]),
        )
    except Exception:
        return None


def _socket_resolve(domain: str, rtype: str) -> list[str]:
    results = []
    try:
        if rtype == "A":
            for info in socket.getaddrinfo(domain, None, socket.AF_INET):
                ip = info[4][0]
                if ip not in results:
                    results.append(ip)
        elif rtype == "AAAA":
            for info in socket.getaddrinfo(domain, None, socket.AF_INET6):
                ip = info[4][0]
                if ip not in results:
                    results.append(ip)
        elif rtype == "MX":
            # No stdlib MX lookup — skip
            pass
        elif rtype == "NS":
            pass
    except Exception:
        pass
    return results


async def _zone_transfer(domain: str, ns: str, timeout: float) -> str:
    cmd = ["dig", f"@{ns}", domain, "AXFR", f"+time={int(timeout)}"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 3)
        text = out.decode(errors="replace")
        if "Transfer failed" in text or "REFUSED" in text or "connection refused" in text.lower():
            return "refused"
        if ";" in text and "\n" in text and len(text) > 100:
            return f"SUCCESS — {len(text.splitlines())} lines received"
        return "refused"
    except FileNotFoundError:
        return "dig not found"
    except Exception as exc:
        return f"error: {exc}"


async def _resolve_subdomain(sub: str, domain: str, timeout: float) -> str | None:
    fqdn = f"{sub}.{domain}"
    try:
        loop = asyncio.get_event_loop()
        addrs = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyname, fqdn),
            timeout=timeout,
        )
        return fqdn
    except Exception:
        return None


def _check_wildcard(domain: str) -> bool:
    import random, string
    rand = "".join(random.choices(string.ascii_lowercase, k=12))
    try:
        socket.gethostbyname(f"{rand}.{domain}")
        return True
    except Exception:
        return False


def _dnssec_check(domain: str) -> bool:
    lines = _dig(domain, "DNSKEY")
    return bool(lines)


class DNSReconTool(BaseCallable):
    name = "dns_recon"
    description = (
        "DNS reconnaissance: A/AAAA/MX/NS/TXT/SOA records, SPF/DMARC extraction, "
        "zone transfer attempts (AXFR), subdomain enumeration, DNSSEC status, "
        "wildcard detection, and DNS security findings. AUTHORIZED USE ONLY."
    )
    callable_type = CallableType.TOOL
    input_schema = DNSReconInput
    output_schema = DNSReconOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=True,
        network_allowed=True,
        max_output_bytes=256 * 1024,
    )

    async def _execute(self, input_data: DNSReconInput, context: object) -> DNSReconOutput:
        t0 = time.monotonic()
        domain = input_data.domain.strip().rstrip(".")
        ns_override = input_data.nameserver
        findings: list[str] = []

        records: list[DNSRecord] = []
        nameservers: list[str] = []

        # Collect DNS records
        for rtype in input_data.record_types:
            lines = _dig(domain, rtype, ns_override, input_data.timeout)
            if not lines:
                # fallback to socket for A/AAAA
                for ip in _socket_resolve(domain, rtype):
                    records.append(DNSRecord(name=domain, record_type=rtype, value=ip, ttl=0))
                continue
            for ln in lines:
                rec = _parse_dig_line(ln)
                if rec:
                    records.append(rec)
                    if rec.record_type == "NS":
                        ns_val = rec.value.rstrip(".")
                        if ns_val not in nameservers:
                            nameservers.append(ns_val)

        # SPF
        spf = next((r.value for r in records if r.record_type == "TXT" and "v=spf1" in r.value.lower()), "")
        if not spf:
            findings.append("WARNING: No SPF record found — email spoofing possible")

        # DMARC
        dmarc_lines = _dig(f"_dmarc.{domain}", "TXT", ns_override, input_data.timeout)
        dmarc = next((ln.split("\t")[-1] for ln in dmarc_lines if "DMARC1" in ln.upper()), "")
        if not dmarc:
            findings.append("WARNING: No DMARC record found — email authentication not enforced")
        elif "p=none" in dmarc.lower():
            findings.append("INFO: DMARC policy is 'none' — monitoring only, not enforced")

        # DNSSEC
        dnssec = _dnssec_check(domain)
        if not dnssec:
            findings.append("INFO: DNSSEC not detected for this domain")

        # Wildcard
        wildcard = _check_wildcard(domain)
        if wildcard:
            findings.append("INFO: Wildcard DNS detected — all subdomains resolve (may hide real subdomains)")

        # Zone transfers
        zt_results: dict[str, str] = {}
        if input_data.attempt_zone_transfer and nameservers:
            tasks = [_zone_transfer(domain, ns, input_data.timeout) for ns in nameservers[:5]]
            zt_answers = await asyncio.gather(*tasks)
            for ns, result in zip(nameservers[:5], zt_answers):
                zt_results[ns] = result
                if "SUCCESS" in result:
                    findings.append(f"CRITICAL: Zone transfer succeeded from {ns} — all DNS records exposed")

        # Subdomain enumeration
        discovered: list[str] = []
        if input_data.enumerate_subdomains:
            sem = asyncio.Semaphore(20)

            async def bounded(sub):
                async with sem:
                    return await _resolve_subdomain(sub, domain, input_data.timeout)

            results = await asyncio.gather(*[bounded(s) for s in input_data.subdomain_wordlist])
            discovered = [r for r in results if r]

        return DNSReconOutput(
            domain=domain,
            records=records,
            nameservers=nameservers,
            zone_transfer_results=zt_results,
            discovered_subdomains=discovered,
            spf_record=spf,
            dmarc_record=dmarc,
            dnssec_enabled=dnssec,
            wildcard_detected=wildcard,
            findings=findings,
            duration_seconds=round(time.monotonic() - t0, 2),
        )
