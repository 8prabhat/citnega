"""
OSFingerprintTool — deep OS and system fingerprinting.

Collects: OS type/version/build, CPU architecture, memory, disk, hostname,
uptime, installed package managers, Python runtime, and cloud provider hints.
Pure Python + stdlib; psutil used opportunistically.
"""

from __future__ import annotations

import os
import platform
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class OSFingerprintInput(BaseModel):
    include_packages: bool = False   # list installed system packages (slow)
    include_hardware: bool = True    # CPU / memory details
    include_cloud: bool = True       # detect AWS / GCP / Azure / k8s


class OSFingerprintOutput(BaseModel):
    os_name: str
    os_version: str
    os_release: str
    kernel_version: str
    architecture: str
    hostname: str
    fqdn: str
    python_version: str
    uptime_seconds: float
    cpu_model: str
    cpu_cores_logical: int
    cpu_cores_physical: int
    ram_total_mb: float
    ram_available_mb: float
    disk_total_gb: float
    disk_free_gb: float
    package_managers: list[str]
    installed_packages_sample: list[str]   # first 50 if requested
    cloud_provider: str
    container_runtime: str
    environment_hints: list[str]


def _uptime() -> float:
    try:
        import psutil
        return time.time() - psutil.boot_time()
    except ImportError:
        pass
    if platform.system() == "Linux":
        try:
            with open("/proc/uptime") as f:
                return float(f.read().split()[0])
        except Exception:
            pass
    return 0.0


def _cpu_info() -> tuple[str, int, int]:
    model, logical, physical = "unknown", os.cpu_count() or 1, 1
    try:
        import psutil
        logical = psutil.cpu_count(logical=True) or logical
        physical = psutil.cpu_count(logical=False) or 1
    except ImportError:
        pass
    if platform.system() == "Linux":
        try:
            for ln in Path("/proc/cpuinfo").read_text().splitlines():
                if ln.startswith("model name"):
                    model = ln.split(":", 1)[1].strip()
                    break
        except Exception:
            pass
    elif platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            )
            model = out.stdout.strip() or model
        except Exception:
            pass
    elif platform.system() == "Windows":
        try:
            out = subprocess.run(
                ["wmic", "cpu", "get", "Name"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in out.stdout.splitlines() if l.strip() and "Name" not in l]
            model = lines[0] if lines else model
        except Exception:
            pass
    return model, logical, physical


def _memory() -> tuple[float, float]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.total / 1024**2, vm.available / 1024**2
    except ImportError:
        pass
    if platform.system() == "Linux":
        try:
            data = {}
            for ln in Path("/proc/meminfo").read_text().splitlines():
                k, v = ln.split(":", 1)
                data[k.strip()] = int(v.strip().split()[0])
            total = data.get("MemTotal", 0) / 1024
            avail = data.get("MemAvailable", 0) / 1024
            return total, avail
        except Exception:
            pass
    return 0.0, 0.0


def _disk() -> tuple[float, float]:
    try:
        import psutil
        d = psutil.disk_usage("/")
        return d.total / 1024**3, d.free / 1024**3
    except ImportError:
        pass
    try:
        st = os.statvfs("/")
        total = st.f_frsize * st.f_blocks / 1024**3
        free = st.f_frsize * st.f_bfree / 1024**3
        return total, free
    except Exception:
        return 0.0, 0.0


def _package_managers() -> list[str]:
    candidates = ["apt", "apt-get", "yum", "dnf", "pacman", "zypper", "brew", "pip3", "conda", "snap", "flatpak"]
    found = []
    for c in candidates:
        try:
            subprocess.run(["which", c], capture_output=True, timeout=2, check=True)
            found.append(c)
        except Exception:
            pass
    return found


def _installed_packages() -> list[str]:
    # Try the fastest method per platform
    for cmd in [
        ["dpkg", "--get-selections"],
        ["rpm", "-qa", "--queryformat", "%{NAME}\\n"],
        ["brew", "list"],
    ]:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            lines = [l.split()[0] for l in out.stdout.splitlines() if l.strip()]
            if lines:
                return sorted(lines)[:50]
        except Exception:
            pass
    return []


def _detect_cloud() -> str:
    # AWS: instance metadata endpoint
    dmi_bios = ""
    if platform.system() == "Linux":
        for p in ["/sys/class/dmi/id/sys_vendor", "/sys/class/dmi/id/board_vendor"]:
            try:
                dmi_bios = Path(p).read_text().strip().lower()
            except Exception:
                pass
        if "amazon" in dmi_bios:
            return "AWS"
        if "google" in dmi_bios:
            return "GCP"
        if "microsoft" in dmi_bios:
            return "Azure"

    # Env-based cloud hints
    if os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"):
        return "AWS"
    if os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCE_METADATA_HOST"):
        return "GCP"
    if os.getenv("AZURE_CLIENT_ID") or os.getenv("MSI_ENDPOINT"):
        return "Azure"
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return "Kubernetes"
    return "bare-metal/unknown"


def _detect_container() -> str:
    if Path("/.dockerenv").exists():
        return "Docker"
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
        if "docker" in cgroup:
            return "Docker"
        if "containerd" in cgroup:
            return "containerd"
        if "lxc" in cgroup.lower():
            return "LXC"
    except Exception:
        pass
    if os.getenv("container") == "podman":
        return "Podman"
    return "none"


def _env_hints() -> list[str]:
    hints = []
    if os.getenv("CI"):
        hints.append("CI environment detected")
    if os.getenv("VIRTUAL_ENV"):
        hints.append(f"Python venv: {os.getenv('VIRTUAL_ENV')}")
    if os.getenv("CONDA_DEFAULT_ENV"):
        hints.append(f"Conda env: {os.getenv('CONDA_DEFAULT_ENV')}")
    if os.getenv("SUDO_USER"):
        hints.append(f"Running under sudo (original user: {os.getenv('SUDO_USER')})")
    if os.geteuid() == 0 if hasattr(os, "geteuid") else False:
        hints.append("Running as root")
    return hints


class OSFingerprintTool(BaseCallable):
    name = "os_fingerprint"
    description = (
        "Deep OS and system fingerprinting: OS version, kernel, CPU/RAM/disk, uptime, "
        "package managers, cloud provider detection, and container runtime identification."
    )
    callable_type = CallableType.TOOL
    input_schema = OSFingerprintInput
    output_schema = OSFingerprintOutput

    async def _execute(self, input_data: OSFingerprintInput, context: object) -> OSFingerprintOutput:
        cpu_model, cpu_logical, cpu_physical = _cpu_info()
        ram_total, ram_avail = _memory()
        disk_total, disk_free = _disk()

        pkgs_sample: list[str] = []
        pkg_managers: list[str] = []
        if input_data.include_packages:
            pkg_managers = _package_managers()
            pkgs_sample = _installed_packages()

        cloud = _detect_cloud() if input_data.include_cloud else "skipped"
        container = _detect_container() if input_data.include_cloud else "skipped"

        return OSFingerprintOutput(
            os_name=platform.system(),
            os_version=platform.version(),
            os_release=platform.release(),
            kernel_version=platform.uname().release,
            architecture=platform.machine(),
            hostname=socket.gethostname(),
            fqdn=socket.getfqdn(),
            python_version=sys.version,
            uptime_seconds=_uptime(),
            cpu_model=cpu_model if input_data.include_hardware else "",
            cpu_cores_logical=cpu_logical if input_data.include_hardware else 0,
            cpu_cores_physical=cpu_physical if input_data.include_hardware else 0,
            ram_total_mb=round(ram_total, 1) if input_data.include_hardware else 0,
            ram_available_mb=round(ram_avail, 1) if input_data.include_hardware else 0,
            disk_total_gb=round(disk_total, 2) if input_data.include_hardware else 0,
            disk_free_gb=round(disk_free, 2) if input_data.include_hardware else 0,
            package_managers=pkg_managers,
            installed_packages_sample=pkgs_sample,
            cloud_provider=cloud,
            container_runtime=container,
            environment_hints=_env_hints(),
        )
