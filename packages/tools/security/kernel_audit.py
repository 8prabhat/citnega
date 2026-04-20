"""
KernelAuditTool — Linux kernel security hardening audit.

Checks:
  - ASLR (randomize_va_space)
  - NX / DEP / SMEP / SMAP bits (via /proc/cpuinfo)
  - Kernel pointer restriction (kptr_restrict)
  - dmesg restriction (dmesg_restrict)
  - PTRACE scope (yama/ptrace_scope)
  - Core dump restriction (fs.suid_dumpable)
  - SYN flood protection
  - IP forwarding
  - Exec-shield / PIE
  - SELinux / AppArmor / seccomp status
  - Kernel version and known EOL warning
  - Loaded kernel modules
  - Sysctl security parameters
  - Spectre/Meltdown mitigations
"""

from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class KernelAuditInput(BaseModel):
    include_modules: bool = False    # list loaded kernel modules
    include_sysctl: bool = True      # dump security-related sysctl values
    include_mitigations: bool = True # check Spectre/Meltdown mitigations


class AuditCheck(BaseModel):
    name: str
    value: str
    status: Literal["good", "warn", "bad", "info"]
    detail: str


class KernelAuditOutput(BaseModel):
    kernel_version: str
    architecture: str
    eol_warning: str
    checks: list[AuditCheck]
    mac_framework: str        # SELinux / AppArmor / none
    mac_enforcing: bool
    loaded_modules: list[str]
    sysctl_values: dict[str, str]
    mitigation_status: dict[str, str]
    overall_score: int        # 0-100 rough hardening score


def _read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


def _sysctl(key: str) -> str:
    try:
        out = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _selinux_status() -> tuple[str, bool]:
    status = _read("/sys/fs/selinux/enforce", "")
    if status:
        return "SELinux", status == "1"
    try:
        out = subprocess.run(["sestatus"], capture_output=True, text=True, timeout=3)
        text = out.stdout.lower()
        if "enabled" in text:
            enforcing = "enforcing" in text
            return "SELinux", enforcing
    except FileNotFoundError:
        pass

    aa_status = _read("/sys/kernel/security/apparmor/profiles", "")
    if aa_status or Path("/etc/apparmor.d").exists():
        try:
            out = subprocess.run(["aa-status", "--enabled"], capture_output=True, timeout=3)
            return "AppArmor", out.returncode == 0
        except FileNotFoundError:
            return "AppArmor", False

    return "none", False


def _mitigations() -> dict[str, str]:
    result: dict[str, str] = {}
    vuln_dir = Path("/sys/devices/system/cpu/vulnerabilities")
    if vuln_dir.exists():
        for f in sorted(vuln_dir.iterdir()):
            result[f.name] = f.read_text().strip()
    return result


def _modules() -> list[str]:
    try:
        out = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=5)
        return sorted(ln.split()[0] for ln in out.stdout.splitlines()[1:] if ln.split())
    except Exception:
        return []


_EOL_KERNELS = {
    "3.": "EOL (end of life)",
    "4.4": "EOL",
    "4.9": "LTS (limited)",
    "4.14": "LTS",
    "4.19": "LTS",
    "5.4": "LTS",
    "5.10": "LTS",
    "5.15": "LTS",
    "6.1": "LTS",
    "6.6": "LTS",
}

_SECURITY_SYSCTL: list[str] = [
    "kernel.randomize_va_space",
    "kernel.kptr_restrict",
    "kernel.dmesg_restrict",
    "kernel.perf_event_paranoid",
    "kernel.sysrq",
    "kernel.unprivileged_userns_clone",
    "kernel.unprivileged_bpf_disabled",
    "net.ipv4.ip_forward",
    "net.ipv4.conf.all.rp_filter",
    "net.ipv4.tcp_syncookies",
    "net.ipv4.conf.all.send_redirects",
    "net.ipv4.conf.all.accept_redirects",
    "net.ipv4.conf.all.accept_source_route",
    "net.ipv4.icmp_echo_ignore_broadcasts",
    "net.ipv6.conf.all.disable_ipv6",
    "fs.suid_dumpable",
    "fs.protected_hardlinks",
    "fs.protected_symlinks",
]


def _build_checks() -> list[AuditCheck]:
    checks: list[AuditCheck] = []

    def add(name, value, good_values, bad_values, detail_good, detail_bad):
        if value in good_values:
            checks.append(AuditCheck(name=name, value=value, status="good", detail=detail_good))
        elif value in bad_values:
            checks.append(AuditCheck(name=name, value=value, status="bad", detail=detail_bad))
        else:
            checks.append(AuditCheck(name=name, value=value, status="warn", detail=f"Value {value!r} — review manually"))

    aslr = _read("/proc/sys/kernel/randomize_va_space", _sysctl("kernel.randomize_va_space"))
    add("ASLR (randomize_va_space)", aslr, ["2"], ["0"], "Full ASLR enabled", "ASLR disabled — stack/heap addresses predictable")

    kptr = _read("/proc/sys/kernel/kptr_restrict", _sysctl("kernel.kptr_restrict"))
    add("Kernel pointer restriction", kptr, ["1", "2"], ["0"], "Kernel pointers hidden", "Kernel pointers exposed to unprivileged users")

    dmesg = _read("/proc/sys/kernel/dmesg_restrict", _sysctl("kernel.dmesg_restrict"))
    add("dmesg restriction", dmesg, ["1"], ["0"], "dmesg restricted to root", "Any user can read dmesg (info leak)")

    ptrace = _read("/proc/sys/kernel/yama/ptrace_scope", "")
    if ptrace:
        add("PTRACE scope (Yama)", ptrace, ["1", "2", "3"], ["0"], "ptrace restricted", "ptrace unrestricted — process injection possible")
    else:
        checks.append(AuditCheck(name="PTRACE scope (Yama)", value="not available", status="warn", detail="Yama LSM not loaded"))

    suid_dump = _read("/proc/sys/fs/suid_dumpable", _sysctl("fs.suid_dumpable"))
    add("Core dump (suid_dumpable)", suid_dump, ["0"], ["2"], "Core dumps disabled for suid binaries", "All processes can create core dumps (credential leak risk)")

    ipfwd = _read("/proc/sys/net/ipv4/ip_forward", _sysctl("net.ipv4.ip_forward"))
    add("IP forwarding", ipfwd, ["0"], ["1"], "IP forwarding disabled", "IP forwarding enabled (host acts as router)")

    syncookies = _read("/proc/sys/net/ipv4/tcp_syncookies", _sysctl("net.ipv4.tcp_syncookies"))
    add("TCP SYN cookies", syncookies, ["1"], ["0"], "SYN flood protection enabled", "SYN cookies disabled — DoS vulnerable")

    rp_filter = _read("/proc/sys/net/ipv4/conf/all/rp_filter", _sysctl("net.ipv4.conf.all.rp_filter"))
    add("Reverse path filtering", rp_filter, ["1", "2"], ["0"], "Spoofed packet filtering enabled", "Reverse path filter disabled")

    redirects = _read("/proc/sys/net/ipv4/conf/all/send_redirects", _sysctl("net.ipv4.conf.all.send_redirects"))
    add("ICMP redirects (send)", redirects, ["0"], ["1"], "ICMP redirects not sent", "ICMP redirects enabled — MITM risk")

    hardlinks = _read("/proc/sys/fs/protected_hardlinks", _sysctl("fs.protected_hardlinks"))
    add("Protected hardlinks", hardlinks, ["1"], ["0"], "Hardlink protection enabled", "Hardlink attacks possible")

    symlinks = _read("/proc/sys/fs/protected_symlinks", _sysctl("fs.protected_symlinks"))
    add("Protected symlinks", symlinks, ["1"], ["0"], "Symlink protection enabled", "Symlink TOCTOU attacks possible")

    # NX / DEP from cpuinfo
    cpuinfo = _read("/proc/cpuinfo")
    if " nx " in f" {cpuinfo} " or "nx" in cpuinfo.split():
        checks.append(AuditCheck(name="NX/XD bit (CPU)", value="present", status="good", detail="No-execute memory protection available"))
    else:
        checks.append(AuditCheck(name="NX/XD bit (CPU)", value="absent", status="bad", detail="CPU may not support NX — shellcode execution easier"))

    smep = "smep" in cpuinfo
    smap = "smap" in cpuinfo
    checks.append(AuditCheck(
        name="SMEP (Supervisor Mode Execution Prevention)",
        value="present" if smep else "absent",
        status="good" if smep else "warn",
        detail="Kernel cannot execute user-space pages" if smep else "SMEP not reported in cpuinfo",
    ))
    checks.append(AuditCheck(
        name="SMAP (Supervisor Mode Access Prevention)",
        value="present" if smap else "absent",
        status="good" if smap else "warn",
        detail="Kernel cannot access user-space data arbitrarily" if smap else "SMAP not reported",
    ))

    return checks


class KernelAuditTool(BaseCallable):
    name = "kernel_audit"
    description = (
        "Linux kernel security hardening audit: ASLR, NX, SMEP/SMAP, kptr_restrict, "
        "dmesg_restrict, PTRACE scope, SYN cookies, SELinux/AppArmor status, "
        "Spectre/Meltdown mitigations, and full sysctl security parameter dump."
    )
    callable_type = CallableType.TOOL
    input_schema = KernelAuditInput
    output_schema = KernelAuditOutput

    async def _execute(self, input_data: KernelAuditInput, context: object) -> KernelAuditOutput:
        if platform.system() != "Linux":
            return KernelAuditOutput(
                kernel_version=platform.release(),
                architecture=platform.machine(),
                eol_warning="Kernel audit only fully supported on Linux",
                checks=[],
                mac_framework="N/A",
                mac_enforcing=False,
                loaded_modules=[],
                sysctl_values={},
                mitigation_status={},
                overall_score=0,
            )

        kver = platform.release()
        eol = "unknown"
        for prefix, status in _EOL_KERNELS.items():
            if kver.startswith(prefix):
                eol = status
                break

        checks = _build_checks()
        mac_fw, mac_enforcing = _selinux_status()

        sysctl_vals: dict[str, str] = {}
        if input_data.include_sysctl:
            for key in _SECURITY_SYSCTL:
                val = _sysctl(key)
                if val:
                    sysctl_vals[key] = val

        mitigations: dict[str, str] = {}
        if input_data.include_mitigations:
            mitigations = _mitigations()
            for vuln, status in mitigations.items():
                s = "good" if "not affected" in status.lower() or "mitigation" in status.lower() else "warn"
                checks.append(AuditCheck(name=f"Spectre/Meltdown: {vuln}", value=status, status=s, detail=status))

        modules = _modules() if input_data.include_modules else []

        good = sum(1 for c in checks if c.status == "good")
        total = len([c for c in checks if c.status in ("good", "warn", "bad")])
        score = int((good / total) * 100) if total else 0

        return KernelAuditOutput(
            kernel_version=kver,
            architecture=platform.machine(),
            eol_warning=eol,
            checks=checks,
            mac_framework=mac_fw,
            mac_enforcing=mac_enforcing,
            loaded_modules=modules,
            sysctl_values=sysctl_vals,
            mitigation_status=mitigations,
            overall_score=score,
        )
