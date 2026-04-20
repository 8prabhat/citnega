"""
HypervisorDetectTool — detect virtualization, hypervisor type, and container runtime.

Checks: DMI/SMBIOS data, CPUID leaves, /proc/cpuinfo hypervisor flag,
kernel module list, environment variables, /.dockerenv, cgroup hierarchy.

Covers: VMware, KVM/QEMU, VirtualBox, Hyper-V, Xen, Parallels, BHYVE,
Docker, containerd, Podman, LXC/LXD, WSL, and cloud bare-metal instances.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class HypervisorDetectInput(BaseModel):
    deep_scan: bool = True   # read DMI, check CPUID via dmidecode/virt-what if present


class HypervisorFinding(BaseModel):
    source: str       # where the evidence was found
    indicator: str    # raw evidence string
    hypervisor: str   # interpreted label


class HypervisorDetectOutput(BaseModel):
    hypervisor: str               # primary determination
    confidence: str               # high / medium / low
    is_virtual: bool
    is_container: bool
    wsl: bool
    findings: list[HypervisorFinding]
    dmi_info: dict[str, str]
    virt_what_output: str


_VENDOR_MAP: dict[str, str] = {
    "vmware":       "VMware",
    "virtualbox":   "VirtualBox",
    "innotek":      "VirtualBox",
    "qemu":         "QEMU/KVM",
    "kvm":          "KVM",
    "microsoft":    "Hyper-V",
    "xen":          "Xen",
    "parallels":    "Parallels",
    "bhyve":        "bhyve",
    "bochs":        "QEMU/Bochs",
    "ovmf":         "QEMU/OVMF",
    "amazon":       "AWS/Xen",
    "google":       "GCP/KVM",
}


def _dmi_info() -> dict[str, str]:
    fields = {
        "sys_vendor":    "/sys/class/dmi/id/sys_vendor",
        "product_name":  "/sys/class/dmi/id/product_name",
        "product_version": "/sys/class/dmi/id/product_version",
        "board_vendor":  "/sys/class/dmi/id/board_vendor",
        "bios_vendor":   "/sys/class/dmi/id/bios_vendor",
        "chassis_vendor": "/sys/class/dmi/id/chassis_vendor",
    }
    result = {}
    for key, path in fields.items():
        try:
            result[key] = Path(path).read_text().strip()
        except Exception:
            result[key] = ""
    return result


def _cpuinfo_flags() -> str:
    try:
        return Path("/proc/cpuinfo").read_text()
    except Exception:
        return ""


def _run_virt_what() -> str:
    for cmd in [["virt-what"], ["systemd-detect-virt"]]:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
        except FileNotFoundError:
            continue
        except Exception:
            break
    return ""


def _kernel_modules() -> list[str]:
    try:
        out = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=5)
        return [ln.split()[0].lower() for ln in out.stdout.splitlines() if ln.split()]
    except Exception:
        return []


def _check_container() -> tuple[bool, str]:
    if Path("/.dockerenv").exists():
        return True, "Docker"
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
        for keyword in ["docker", "containerd", "lxc", "kubepods"]:
            if keyword in cgroup.lower():
                return True, keyword.capitalize()
    except Exception:
        pass
    if os.getenv("container") == "podman":
        return True, "Podman"
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return True, "Kubernetes"
    return False, ""


def _check_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        pass
    return "WSL" in os.getenv("WSL_DISTRO_NAME", "") or bool(os.getenv("WSL_INTEROP"))


def _darwin_vm() -> list[HypervisorFinding]:
    findings = []
    try:
        out = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10,
        )
        text = out.stdout.lower()
        for vendor, label in _VENDOR_MAP.items():
            if vendor in text:
                findings.append(HypervisorFinding(source="system_profiler", indicator=vendor, hypervisor=label))
    except Exception:
        pass
    return findings


class HypervisorDetectTool(BaseCallable):
    name = "hypervisor_detect"
    description = (
        "Detect hypervisor type (VMware, KVM, VirtualBox, Hyper-V, Xen, etc.), "
        "container runtime (Docker, Podman, LXC, k8s), and WSL. "
        "Reads DMI/SMBIOS, /proc/cpuinfo, cgroup hierarchy, and kernel modules."
    )
    callable_type = CallableType.TOOL
    input_schema = HypervisorDetectInput
    output_schema = HypervisorDetectOutput

    async def _execute(self, input_data: HypervisorDetectInput, context: object) -> HypervisorDetectOutput:
        findings: list[HypervisorFinding] = []
        system = platform.system()

        # Container / WSL checks (cross-platform)
        is_container, container_name = _check_container()
        is_wsl = _check_wsl()
        if is_container:
            findings.append(HypervisorFinding(
                source="cgroup/env", indicator=container_name, hypervisor=container_name
            ))
        if is_wsl:
            findings.append(HypervisorFinding(
                source="/proc/version", indicator="Microsoft", hypervisor="WSL"
            ))

        dmi: dict[str, str] = {}
        virt_what = ""

        if system == "Linux":
            dmi = _dmi_info()
            for key, value in dmi.items():
                vl = value.lower()
                for vendor, label in _VENDOR_MAP.items():
                    if vendor in vl:
                        findings.append(HypervisorFinding(source=f"dmi/{key}", indicator=value, hypervisor=label))

            # /proc/cpuinfo hypervisor flag
            cpuinfo = _cpuinfo_flags()
            if "hypervisor" in cpuinfo:
                # Extract vendor_id
                for ln in cpuinfo.splitlines():
                    if ln.startswith("vendor_id"):
                        vid = ln.split(":", 1)[1].strip().lower()
                        for vendor, label in _VENDOR_MAP.items():
                            if vendor in vid:
                                findings.append(HypervisorFinding(source="/proc/cpuinfo", indicator=vid, hypervisor=label))
                if not findings:
                    findings.append(HypervisorFinding(source="/proc/cpuinfo", indicator="hypervisor flag set", hypervisor="unknown VM"))

            # Kernel modules
            mods = _kernel_modules()
            for mod in mods:
                for vendor, label in _VENDOR_MAP.items():
                    if vendor in mod:
                        findings.append(HypervisorFinding(source="lsmod", indicator=mod, hypervisor=label))

            if input_data.deep_scan:
                virt_what = _run_virt_what()
                if virt_what:
                    for line in virt_what.splitlines():
                        findings.append(HypervisorFinding(source="virt-what/systemd-detect-virt", indicator=line, hypervisor=line))

        elif system == "Darwin":
            findings.extend(_darwin_vm())

        elif system == "Windows":
            # Check via WMI if available
            try:
                out = subprocess.run(
                    ["wmic", "computersystem", "get", "Model,Manufacturer"],
                    capture_output=True, text=True, timeout=10,
                )
                text = out.stdout.lower()
                for vendor, label in _VENDOR_MAP.items():
                    if vendor in text:
                        findings.append(HypervisorFinding(source="wmic", indicator=text[:100], hypervisor=label))
                dmi["wmic"] = out.stdout.strip()[:200]
            except Exception:
                pass

        # Determine primary hypervisor
        labels = [f.hypervisor for f in findings]
        if labels:
            hypervisor = max(set(labels), key=labels.count)
        elif is_wsl:
            hypervisor = "WSL"
        else:
            hypervisor = "none (likely bare-metal)"

        is_virtual = bool(findings) and not (is_container and not is_wsl and len(findings) == 1 and findings[0].hypervisor in ("Docker", "Podman", "Kubernetes", "LXC"))
        confidence = "high" if virt_what or (dmi and any(dmi.values())) else ("medium" if findings else "low")

        return HypervisorDetectOutput(
            hypervisor=hypervisor,
            confidence=confidence,
            is_virtual=is_virtual,
            is_container=is_container,
            wsl=is_wsl,
            findings=findings,
            dmi_info=dmi,
            virt_what_output=virt_what,
        )
