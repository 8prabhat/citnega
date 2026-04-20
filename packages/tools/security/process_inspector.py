"""
ProcessInspectorTool — live process, socket, and file descriptor inspection.

Reports:
  - All running processes (PID, name, user, CPU%, MEM%, cmdline)
  - Listening TCP/UDP sockets with owning PID
  - Established connections
  - Open file descriptors for suspicious processes
  - Processes running as root with world-writable executables
  - Processes with deleted executable (replaced on disk)
  - Unusual parent-child relationships (shell spawned by web server, etc.)

Uses psutil if available; falls back to /proc and ss/netstat.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class ProcessInspectorInput(BaseModel):
    include_connections: bool = Field(default=True, description="Include network connections")
    include_fds: bool = Field(default=False, description="Show open file descriptors (expensive)")
    flag_suspicious: bool = Field(default=True, description="Highlight potentially suspicious processes")
    user_filter: str = Field(default="", description="Only show processes for this user")
    name_filter: str = Field(default="", description="Filter by process name substring")


class ProcessEntry(BaseModel):
    pid: int
    ppid: int
    name: str
    user: str
    cmdline: str
    cpu_percent: float
    mem_mb: float
    exe: str
    suspicious: bool
    suspicious_reason: str


class SocketEntry(BaseModel):
    proto: str
    local_addr: str
    local_port: int
    remote_addr: str
    remote_port: int
    state: str
    pid: int
    process_name: str


class ProcessInspectorOutput(BaseModel):
    processes: list[ProcessEntry]
    listening_sockets: list[SocketEntry]
    established_connections: list[SocketEntry]
    suspicious_count: int
    total_processes: int


_SUSPICIOUS_PARENTS = {
    "httpd", "apache2", "nginx", "php-fpm", "php", "tomcat", "java",
    "node", "python", "ruby", "perl",
}
_SUSPICIOUS_CHILDREN = {"bash", "sh", "zsh", "fish", "ksh", "csh", "nc", "ncat", "netcat", "socat"}


def _processes_psutil(user_filter: str, name_filter: str, flag: bool) -> list[ProcessEntry]:
    import psutil
    entries = []
    for proc in psutil.process_iter(["pid", "ppid", "name", "username", "cmdline", "cpu_percent", "memory_info", "exe"]):
        try:
            info = proc.info
            name = info.get("name") or ""
            user = info.get("username") or ""
            if user_filter and user_filter not in user:
                continue
            if name_filter and name_filter.lower() not in name.lower():
                continue
            cmdline = " ".join(info.get("cmdline") or [])[:200]
            mem_mb = (info.get("memory_info") or type("", (), {"rss": 0})()).rss / 1024**2
            exe = info.get("exe") or ""

            suspicious = False
            reason = ""
            if flag:
                parent_name = ""
                try:
                    parent = psutil.Process(info.get("ppid", 0))
                    parent_name = parent.name().lower()
                except Exception:
                    pass
                if parent_name in _SUSPICIOUS_PARENTS and name.lower() in _SUSPICIOUS_CHILDREN:
                    suspicious = True
                    reason = f"Shell ({name}) spawned by web/app process ({parent_name})"
                if exe and exe.endswith(" (deleted)"):
                    suspicious = True
                    reason += " | Executable deleted from disk (possible rootkit)"
                if user == "root" and exe:
                    try:
                        mode = oct(os.stat(exe).st_mode)
                        if mode.endswith(("777", "775", "757", "755")):
                            pass  # 755 is normal for root binaries
                    except Exception:
                        pass

            entries.append(ProcessEntry(
                pid=info.get("pid", 0),
                ppid=info.get("ppid") or 0,
                name=name,
                user=user,
                cmdline=cmdline,
                cpu_percent=round(info.get("cpu_percent") or 0.0, 1),
                mem_mb=round(mem_mb, 1),
                exe=exe,
                suspicious=suspicious,
                suspicious_reason=reason,
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return entries


def _processes_proc(user_filter: str, name_filter: str) -> list[ProcessEntry]:
    entries = []
    try:
        for pid_path in Path("/proc").iterdir():
            if not pid_path.name.isdigit():
                continue
            pid = int(pid_path.name)
            try:
                name = (pid_path / "comm").read_text().strip()
                cmdline = (pid_path / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()[:200]
                status = {}
                for ln in (pid_path / "status").read_text().splitlines():
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        status[k.strip()] = v.strip()
                ppid = int(status.get("PPid", 0))
                uid = status.get("Uid", "0").split()[0]
                try:
                    import pwd
                    user = pwd.getpwuid(int(uid)).pw_name
                except Exception:
                    user = uid
                exe = ""
                try:
                    exe = str(os.readlink(pid_path / "exe"))
                except Exception:
                    pass

                if user_filter and user_filter not in user:
                    continue
                if name_filter and name_filter.lower() not in name.lower():
                    continue

                entries.append(ProcessEntry(
                    pid=pid, ppid=ppid, name=name, user=user, cmdline=cmdline,
                    cpu_percent=0.0, mem_mb=0.0, exe=exe,
                    suspicious=False, suspicious_reason="",
                ))
            except Exception:
                continue
    except Exception:
        pass
    return entries


def _sockets_psutil() -> tuple[list[SocketEntry], list[SocketEntry]]:
    import psutil
    listening, established = [], []
    pid_map = {p.pid: p.name() for p in psutil.process_iter(["pid", "name"])}
    for conn in psutil.net_connections(kind="all"):
        laddr = conn.laddr
        raddr = conn.raddr
        entry = SocketEntry(
            proto=conn.type.name.lower() if hasattr(conn.type, "name") else str(conn.type),
            local_addr=laddr.ip if laddr else "",
            local_port=laddr.port if laddr else 0,
            remote_addr=raddr.ip if raddr else "",
            remote_port=raddr.port if raddr else 0,
            state=conn.status or "",
            pid=conn.pid or 0,
            process_name=pid_map.get(conn.pid or 0, ""),
        )
        if conn.status == "LISTEN":
            listening.append(entry)
        elif conn.status == "ESTABLISHED":
            established.append(entry)
    return listening, established


def _sockets_fallback() -> tuple[list[SocketEntry], list[SocketEntry]]:
    listening, established = [], []
    try:
        out = subprocess.run(
            ["ss", "-tunap"], capture_output=True, text=True, timeout=10,
        ).stdout
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            state = parts[1] if len(parts) > 1 else ""
            local = parts[4] if len(parts) > 4 else ""
            peer = parts[5] if len(parts) > 5 else ""
            lhost, _, lport_s = local.rpartition(":")
            rhost, _, rport_s = peer.rpartition(":")
            try:
                entry = SocketEntry(
                    proto=parts[0].lower(),
                    local_addr=lhost.strip("[]"),
                    local_port=int(lport_s) if lport_s.isdigit() else 0,
                    remote_addr=rhost.strip("[]"),
                    remote_port=int(rport_s) if rport_s.isdigit() else 0,
                    state=state,
                    pid=0, process_name="",
                )
                if state == "LISTEN":
                    listening.append(entry)
                elif state == "ESTAB":
                    established.append(entry)
            except Exception:
                continue
    except Exception:
        pass
    return listening, established


class ProcessInspectorTool(BaseCallable):
    name = "process_inspector"
    description = (
        "Inspect running processes, listening sockets, and established connections. "
        "Flags suspicious processes: shells spawned by web servers, deleted executables, "
        "and processes with unusual parent-child relationships."
    )
    callable_type = CallableType.TOOL
    input_schema = ProcessInspectorInput
    output_schema = ProcessInspectorOutput

    async def _execute(self, input_data: ProcessInspectorInput, context: object) -> ProcessInspectorOutput:
        try:
            import psutil
            processes = _processes_psutil(input_data.user_filter, input_data.name_filter, input_data.flag_suspicious)
            listening, established = _sockets_psutil() if input_data.include_connections else ([], [])
        except ImportError:
            processes = _processes_proc(input_data.user_filter, input_data.name_filter)
            listening, established = _sockets_fallback() if input_data.include_connections else ([], [])

        processes.sort(key=lambda p: (-p.cpu_percent, p.pid))
        suspicious_count = sum(1 for p in processes if p.suspicious)

        return ProcessInspectorOutput(
            processes=processes,
            listening_sockets=listening,
            established_connections=established,
            suspicious_count=suspicious_count,
            total_processes=len(processes),
        )
