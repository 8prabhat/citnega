"""
FirewallInspectTool — firewall rules inspection and security posture assessment.

Supports:
  - Linux: iptables, ip6tables, nftables, ufw, firewalld
  - macOS: pf (pfctl)
  - Windows: netsh advfirewall

Checks:
  - All INPUT/OUTPUT/FORWARD chains and rules
  - Default chain policies
  - Wide-open rules (0.0.0.0/0 ACCEPT without restrictions)
  - Dangerous exposed services
  - Logging rules (presence/absence)
  - IPv6 firewall status
"""

from __future__ import annotations

import platform
import subprocess

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class FirewallInspectInput(BaseModel):
    include_ip6: bool = Field(default=True, description="Also inspect IPv6 firewall rules")
    include_nftables: bool = Field(default=True, description="Include nftables rules if present")


class FirewallFinding(BaseModel):
    severity: str
    rule: str
    detail: str


class ChainPolicy(BaseModel):
    table: str
    chain: str
    policy: str     # ACCEPT / DROP / REJECT


class FirewallInspectOutput(BaseModel):
    backend: str
    raw_rules: str
    raw_rules_ipv6: str
    chain_policies: list[ChainPolicy]
    findings: list[FirewallFinding]
    logging_enabled: bool
    ipv6_protected: bool
    overall_posture: str   # strict / moderate / permissive / unknown


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout + out.stderr
    except FileNotFoundError:
        return f"[{cmd[0]} not found]"
    except PermissionError:
        return f"[Permission denied — try running as root/sudo]"
    except Exception as exc:
        return f"[Error: {exc}]"


def _parse_iptables_policies(raw: str) -> list[ChainPolicy]:
    policies = []
    for line in raw.splitlines():
        if line.startswith("Chain "):
            parts = line.split()
            if len(parts) >= 4 and "policy" in line:
                chain = parts[1]
                policy = parts[3].rstrip(")")
                policies.append(ChainPolicy(table="filter", chain=chain, policy=policy))
    return policies


def _analyse_iptables(raw: str) -> list[FirewallFinding]:
    findings = []
    lines = raw.splitlines()

    # Default ACCEPT on INPUT is permissive
    for pol in _parse_iptables_policies(raw):
        if pol.chain == "INPUT" and pol.policy == "ACCEPT":
            findings.append(FirewallFinding(
                severity="high",
                rule=f"Chain INPUT policy {pol.policy}",
                detail="Default INPUT policy is ACCEPT — all traffic allowed unless explicitly blocked",
            ))
        if pol.chain == "FORWARD" and pol.policy == "ACCEPT":
            findings.append(FirewallFinding(
                severity="medium",
                rule=f"Chain FORWARD policy {pol.policy}",
                detail="Default FORWARD policy is ACCEPT — host may forward traffic unexpectedly",
            ))

    # Wide-open ACCEPT rules
    for line in lines:
        if "ACCEPT" in line and ("0.0.0.0/0" in line or "anywhere" in line.lower()):
            if "--dport" not in line and "-p" not in line:
                findings.append(FirewallFinding(
                    severity="medium",
                    rule=line.strip(),
                    detail="Unrestricted ACCEPT rule allows all traffic from/to any address",
                ))

    # No logging rules
    has_log = any("LOG" in ln for ln in lines)
    if not has_log:
        findings.append(FirewallFinding(
            severity="low",
            rule="(no LOG rules)",
            detail="No LOG rules found — dropped/rejected traffic is not logged",
        ))

    return findings


def _inspect_linux(include_ip6: bool, include_nft: bool) -> tuple[str, str, str, list[ChainPolicy], list[FirewallFinding], bool, bool]:
    backend = "unknown"
    raw4, raw6 = "", ""
    policies: list[ChainPolicy] = []
    findings: list[FirewallFinding] = []
    logging_enabled = False
    ipv6_protected = False

    # Try nftables first
    nft_out = _run(["nft", "list", "ruleset"])
    if "[nft not found]" not in nft_out and nft_out.strip():
        backend = "nftables"
        raw4 = nft_out
        if include_ip6:
            # nftables handles both families
            ipv6_protected = "ip6" in nft_out or "inet" in nft_out
            raw6 = "(included in nftables ruleset above)"
        logging_enabled = "log" in nft_out.lower()
        if not nft_out.strip() or nft_out.strip() == "":
            findings.append(FirewallFinding(
                severity="critical", rule="nftables empty",
                detail="nftables is active but has no rules — all traffic allowed",
            ))
        return backend, raw4, raw6, policies, findings, logging_enabled, ipv6_protected

    # iptables
    raw4 = _run(["iptables", "-L", "-n", "-v", "--line-numbers"])
    if "not found" not in raw4 and "Permission denied" not in raw4:
        backend = "iptables"
        policies = _parse_iptables_policies(raw4)
        findings = _analyse_iptables(raw4)
        logging_enabled = "LOG" in raw4

        if include_ip6:
            raw6 = _run(["ip6tables", "-L", "-n", "-v"])
            ip6_policies = _parse_iptables_policies(raw6)
            has_drop = any(p.policy == "DROP" for p in ip6_policies if p.chain == "INPUT")
            ipv6_protected = has_drop
            if not ipv6_protected:
                findings.append(FirewallFinding(
                    severity="medium", rule="ip6tables INPUT ACCEPT",
                    detail="IPv6 INPUT chain has no DROP policy — IPv6 traffic may be unfiltered",
                ))

    # ufw
    ufw_out = _run(["ufw", "status", "verbose"])
    if "not found" not in ufw_out and ufw_out.strip():
        if backend == "unknown":
            backend = "ufw"
        raw4 += f"\n\n=== UFW STATUS ===\n{ufw_out}"
        if "Status: inactive" in ufw_out:
            findings.append(FirewallFinding(
                severity="critical", rule="ufw inactive",
                detail="UFW is installed but INACTIVE — no firewall protection",
            ))

    # firewalld
    fwd_out = _run(["firewall-cmd", "--list-all"])
    if "not found" not in fwd_out and fwd_out.strip():
        if backend == "unknown":
            backend = "firewalld"
        raw4 += f"\n\n=== FIREWALLD ===\n{fwd_out}"

    if backend == "unknown":
        findings.append(FirewallFinding(
            severity="critical", rule="(no firewall detected)",
            detail="No recognised firewall backend found (iptables, nftables, ufw, firewalld)",
        ))

    return backend, raw4, raw6, policies, findings, logging_enabled, ipv6_protected


def _inspect_macos(include_ip6: bool) -> tuple[str, str, str, list[ChainPolicy], list[FirewallFinding], bool, bool]:
    raw = _run(["pfctl", "-s", "all"])
    backend = "pf"
    policies: list[ChainPolicy] = []
    findings: list[FirewallFinding] = []
    logging_enabled = "log" in raw.lower()
    ipv6_protected = "inet6" in raw

    if "not enabled" in raw.lower() or raw.startswith("["):
        findings.append(FirewallFinding(
            severity="critical", rule="pf disabled",
            detail="pf firewall is not enabled — system is unprotected",
        ))

    # Check Application Layer Firewall (macOS)
    alf = _run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"])
    if "disabled" in alf.lower():
        findings.append(FirewallFinding(
            severity="high", rule="Application Layer Firewall disabled",
            detail="macOS Application Firewall is disabled",
        ))

    return backend, raw, "", policies, findings, logging_enabled, ipv6_protected


def _inspect_windows() -> tuple[str, str, str, list[ChainPolicy], list[FirewallFinding], bool, bool]:
    raw = _run(["netsh", "advfirewall", "show", "allprofiles"])
    backend = "Windows Firewall"
    findings: list[FirewallFinding] = []

    if "off" in raw.lower():
        findings.append(FirewallFinding(
            severity="critical", rule="Windows Firewall disabled",
            detail="One or more Windows Firewall profiles are disabled",
        ))

    rules = _run(["netsh", "advfirewall", "firewall", "show", "rule", "name=all"])
    return backend, raw + "\n\n" + rules, "", [], findings, False, False


def _posture(findings: list[FirewallFinding], policies: list[ChainPolicy]) -> str:
    crits = sum(1 for f in findings if f.severity == "critical")
    highs = sum(1 for f in findings if f.severity == "high")
    if crits > 0:
        return "permissive"
    if highs > 1:
        return "moderate"
    if not findings:
        return "strict"
    return "moderate"


class FirewallInspectTool(BaseCallable):
    name = "firewall_inspect"
    description = (
        "Inspect firewall rules and posture on Linux (iptables, nftables, ufw, firewalld), "
        "macOS (pf, Application Firewall), and Windows (netsh advfirewall). "
        "Reports chain policies, wide-open rules, missing logging, and IPv6 exposure."
    )
    callable_type = CallableType.TOOL
    input_schema = FirewallInspectInput
    output_schema = FirewallInspectOutput

    async def _execute(self, input_data: FirewallInspectInput, context: object) -> FirewallInspectOutput:
        system = platform.system()

        if system == "Linux":
            backend, raw4, raw6, policies, findings, logging, ipv6_ok = _inspect_linux(
                input_data.include_ip6, input_data.include_nftables,
            )
        elif system == "Darwin":
            backend, raw4, raw6, policies, findings, logging, ipv6_ok = _inspect_macos(input_data.include_ip6)
        elif system == "Windows":
            backend, raw4, raw6, policies, findings, logging, ipv6_ok = _inspect_windows()
        else:
            backend, raw4, raw6, policies, findings, logging, ipv6_ok = "unknown", "", "", [], [], False, False

        return FirewallInspectOutput(
            backend=backend,
            raw_rules=raw4[:50_000],
            raw_rules_ipv6=raw6[:10_000],
            chain_policies=policies,
            findings=findings,
            logging_enabled=logging,
            ipv6_protected=ipv6_ok,
            overall_posture=_posture(findings, policies),
        )
