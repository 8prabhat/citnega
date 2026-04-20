"""
NetworkReconTool — network reconnaissance: ping sweep, traceroute, ARP table,
interface enumeration, and active host discovery.

Uses stdlib subprocess + socket only. Requires approval.
"""

from __future__ import annotations

import asyncio
import ipaddress
import platform
import socket
import time

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class NetworkReconInput(BaseModel):
    target: str = Field(description="IP, hostname, or CIDR to probe (e.g. 192.168.1.0/24)")
    ping_sweep: bool = Field(default=True, description="ICMP ping sweep all hosts in range")
    traceroute: bool = Field(default=False, description="Run traceroute to target")
    arp_table: bool = Field(default=True, description="Dump local ARP cache")
    show_interfaces: bool = Field(default=True, description="List local network interfaces")
    dns_reverse: bool = Field(default=True, description="Attempt reverse DNS on discovered hosts")
    ping_count: int = Field(default=1, description="Number of ICMP pings per host")
    timeout: float = Field(default=2.0, description="Per-host ping timeout in seconds")
    max_hosts: int = Field(default=256, description="Cap on hosts in a sweep (safety limit)")


class HostEntry(BaseModel):
    ip: str
    hostname: str
    alive: bool
    rtt_ms: float


class InterfaceEntry(BaseModel):
    name: str
    addresses: list[str]


class NetworkReconOutput(BaseModel):
    target: str
    hosts: list[HostEntry]
    interfaces: list[InterfaceEntry]
    arp_entries: list[str]
    traceroute_lines: list[str]
    duration_seconds: float


async def _ping_host(ip: str, count: int, timeout: float, reverse_dns: bool) -> HostEntry:
    system = platform.system()
    if system == "Windows":
        cmd = ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), ip]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(int(timeout)), ip]

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 1)
        alive = proc.returncode == 0
        rtt = round((time.monotonic() - t0) * 1000, 1)
    except Exception:
        alive, rtt = False, 0.0

    hostname = ""
    if alive and reverse_dns:
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except Exception:
            hostname = ""

    return HostEntry(ip=ip, hostname=hostname, alive=alive, rtt_ms=rtt)


async def _traceroute(target: str) -> list[str]:
    system = platform.system()
    cmd = (
        ["tracert", "-d", target] if system == "Windows"
        else ["traceroute", "-n", "-m", "20", target]
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        return out.decode(errors="replace").splitlines()
    except FileNotFoundError:
        return [f"traceroute/tracert not found"]
    except Exception as exc:
        return [f"traceroute error: {exc}"]


def _arp_table() -> list[str]:
    import subprocess
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True, text=True, timeout=5,
        )
        return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def _interfaces() -> list[InterfaceEntry]:
    try:
        import psutil
        entries = []
        for name, addrs in psutil.net_if_addrs().items():
            addr_strs = [f"{a.address}" for a in addrs if a.address]
            entries.append(InterfaceEntry(name=name, addresses=addr_strs))
        return entries
    except ImportError:
        pass
    # Fallback: parse `ip addr` or `ifconfig`
    import subprocess
    system = platform.system()
    cmd = ["ip", "addr"] if system == "Linux" else ["ifconfig"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        return [InterfaceEntry(name="all", addresses=out.splitlines()[:30])]
    except Exception:
        return []


class NetworkReconTool(BaseCallable):
    name = "network_recon"
    description = (
        "Network reconnaissance: ping sweep, traceroute, ARP table dump, and interface listing. "
        "Discover live hosts in a subnet, map routes, and enumerate local interfaces. "
        "AUTHORIZED USE ONLY."
    )
    callable_type = CallableType.TOOL
    input_schema = NetworkReconInput
    output_schema = NetworkReconOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=True,
        network_allowed=True,
        max_output_bytes=512 * 1024,
    )

    async def _execute(self, input_data: NetworkReconInput, context: object) -> NetworkReconOutput:
        t0 = time.monotonic()

        # Expand CIDR or single host
        try:
            net = ipaddress.ip_network(input_data.target, strict=False)
            hosts = [str(h) for h in list(net.hosts())[: input_data.max_hosts]]
            if not hosts:
                hosts = [str(net.network_address)]
        except ValueError:
            hosts = [input_data.target]

        # Ping sweep
        host_results: list[HostEntry] = []
        if input_data.ping_sweep:
            sem = asyncio.Semaphore(50)

            async def bounded(ip):
                async with sem:
                    return await _ping_host(ip, input_data.ping_count, input_data.timeout, input_data.dns_reverse)

            host_results = list(await asyncio.gather(*[bounded(h) for h in hosts]))
        else:
            # Just resolve the single target
            try:
                resolved = socket.gethostbyname(input_data.target)
                host_results = [HostEntry(ip=resolved, hostname=input_data.target, alive=True, rtt_ms=0.0)]
            except Exception:
                host_results = []

        # Interfaces
        interfaces = _interfaces() if input_data.show_interfaces else []

        # ARP
        arp_entries = _arp_table() if input_data.arp_table else []

        # Traceroute
        trace_lines: list[str] = []
        if input_data.traceroute:
            trace_target = input_data.target.split("/")[0]
            trace_lines = await _traceroute(trace_target)

        return NetworkReconOutput(
            target=input_data.target,
            hosts=host_results,
            interfaces=interfaces,
            arp_entries=arp_entries,
            traceroute_lines=trace_lines,
            duration_seconds=round(time.monotonic() - t0, 2),
        )
