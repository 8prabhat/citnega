"""
PortScannerTool — async TCP/UDP port scanner with banner grabbing.

Uses only asyncio + socket — no nmap required. Falls back to wrapping
nmap if installed and the user requests it explicitly.

Requires explicit approval: scanning hosts you do not own is illegal.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from typing import Literal

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class PortScannerInput(BaseModel):
    target: str = Field(description="IP address, hostname, or CIDR range (e.g. 192.168.1.0/24)")
    ports: str = Field(
        default="22,23,25,53,80,110,143,443,445,993,995,1433,3306,3389,5432,6379,8080,8443,27017",
        description="Comma-separated ports or ranges e.g. '80,443,8000-8100'",
    )
    protocol: Literal["tcp", "udp", "both"] = Field(default="tcp")
    timeout: float = Field(default=1.0, description="Per-port connection timeout in seconds")
    concurrency: int = Field(default=100, description="Max simultaneous probes (1–500)")
    grab_banner: bool = Field(default=True, description="Attempt to read service banner on open TCP ports")
    use_nmap: bool = Field(default=False, description="Use nmap if installed (requires nmap on PATH)")


class PortResult(BaseModel):
    port: int
    protocol: str
    state: str          # open / closed / filtered
    service: str        # guessed service name
    banner: str         # raw banner, empty if none


class PortScannerOutput(BaseModel):
    target: str
    resolved_ip: str
    open_ports: list[PortResult]
    total_scanned: int
    duration_seconds: float
    nmap_used: bool
    raw_nmap: str


_WELL_KNOWN: dict[int, str] = {
    20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp",
    53: "dns", 80: "http", 110: "pop3", 143: "imap", 389: "ldap",
    443: "https", 445: "smb", 465: "smtps", 587: "submission",
    636: "ldaps", 993: "imaps", 995: "pop3s", 1433: "mssql",
    1521: "oracle", 3306: "mysql", 3389: "rdp", 5432: "postgres",
    5900: "vnc", 6379: "redis", 6443: "k8s-api", 8080: "http-alt",
    8443: "https-alt", 8888: "jupyter", 9200: "elasticsearch",
    27017: "mongodb", 27018: "mongodb-shard",
}


def _parse_ports(spec: str) -> list[int]:
    ports: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            ports.extend(range(int(lo), int(hi) + 1))
        else:
            ports.append(int(part))
    return sorted(set(ports))


def _expand_targets(target: str) -> list[str]:
    try:
        net = ipaddress.ip_network(target, strict=False)
        return [str(h) for h in net.hosts()] or [str(net.network_address)]
    except ValueError:
        return [target]


async def _tcp_probe(host: str, port: int, timeout: float, grab: bool) -> PortResult:
    state = "filtered"
    banner = ""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        state = "open"
        if grab:
            try:
                # Send a minimal probe to provoke a banner
                writer.write(b"HEAD / HTTP/1.0\r\n\r\n")
                await asyncio.wait_for(writer.drain(), timeout=1.0)
                raw = await asyncio.wait_for(reader.read(512), timeout=2.0)
                banner = raw.decode(errors="replace").strip()[:200]
            except Exception:
                pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except ConnectionRefusedError:
        state = "closed"
    except (TimeoutError, asyncio.TimeoutError, OSError):
        state = "filtered"
    return PortResult(
        port=port,
        protocol="tcp",
        state=state,
        service=_WELL_KNOWN.get(port, "unknown"),
        banner=banner,
    )


async def _udp_probe(host: str, port: int, timeout: float) -> PortResult:
    state = "open|filtered"
    try:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[bytes] = loop.create_future()

        def _protocol_factory():
            class _P(asyncio.DatagramProtocol):
                def datagram_received(self, data, addr):
                    if not fut.done():
                        fut.set_result(data)
                def error_received(self, exc):
                    if not fut.done():
                        fut.set_exception(exc)
            return _P()

        transport, _ = await loop.create_datagram_endpoint(
            _protocol_factory,
            remote_addr=(host, port),
        )
        transport.sendto(b"\x00")
        try:
            await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
            state = "open"
        except (TimeoutError, asyncio.TimeoutError):
            state = "open|filtered"
        except OSError as e:
            import errno
            if e.errno in (errno.ECONNREFUSED, 111):
                state = "closed"
        finally:
            transport.close()
    except Exception:
        pass
    return PortResult(
        port=port,
        protocol="udp",
        state=state,
        service=_WELL_KNOWN.get(port, "unknown"),
        banner="",
    )


async def _run_nmap(target: str, ports: list[int]) -> str:
    port_arg = ",".join(str(p) for p in ports)
    try:
        proc = await asyncio.create_subprocess_exec(
            "nmap", "-sV", "--open", "-T4", "-p", port_arg, target,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        return out.decode(errors="replace")
    except FileNotFoundError:
        return "nmap not found on PATH"
    except Exception as exc:
        return f"nmap error: {exc}"


class PortScannerTool(BaseCallable):
    name = "port_scanner"
    description = (
        "Async TCP/UDP port scanner with service detection and optional banner grabbing. "
        "Supports single hosts, ranges, and CIDR notation. "
        "AUTHORIZED USE ONLY — only scan systems you own or have written permission to test."
    )
    callable_type = CallableType.TOOL
    input_schema = PortScannerInput
    output_schema = PortScannerOutput
    policy = CallablePolicy(
        timeout_seconds=300.0,
        requires_approval=True,
        network_allowed=True,
        max_output_bytes=512 * 1024,
    )

    async def _execute(self, input_data: PortScannerInput, context: object) -> PortScannerOutput:
        t0 = time.monotonic()
        targets = _expand_targets(input_data.target)
        ports = _parse_ports(input_data.ports)
        concurrency = max(1, min(input_data.concurrency, 500))

        # Resolve a display IP
        try:
            resolved_ip = socket.gethostbyname(input_data.target.split("/")[0])
        except Exception:
            resolved_ip = input_data.target

        if input_data.use_nmap:
            raw_nmap = await _run_nmap(input_data.target, ports)
            return PortScannerOutput(
                target=input_data.target,
                resolved_ip=resolved_ip,
                open_ports=[],
                total_scanned=len(ports) * len(targets),
                duration_seconds=round(time.monotonic() - t0, 2),
                nmap_used=True,
                raw_nmap=raw_nmap,
            )

        sem = asyncio.Semaphore(concurrency)
        open_ports: list[PortResult] = []

        async def bounded(coro):
            async with sem:
                return await coro

        tasks = []
        for host in targets:
            if input_data.protocol in ("tcp", "both"):
                for p in ports:
                    tasks.append(bounded(_tcp_probe(host, p, input_data.timeout, input_data.grab_banner)))
            if input_data.protocol in ("udp", "both"):
                for p in ports:
                    tasks.append(bounded(_udp_probe(host, p, input_data.timeout)))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, PortResult) and r.state not in ("closed", "filtered"):
                open_ports.append(r)

        open_ports.sort(key=lambda x: (x.protocol, x.port))

        return PortScannerOutput(
            target=input_data.target,
            resolved_ip=resolved_ip,
            open_ports=open_ports,
            total_scanned=len(tasks),
            duration_seconds=round(time.monotonic() - t0, 2),
            nmap_used=False,
            raw_nmap="",
        )
