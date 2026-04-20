"""Unit tests for security tools — no network, no root privileges required."""

from __future__ import annotations

import asyncio
import platform
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.tools.security import ALL_SECURITY_TOOLS


# ── Shared fake infrastructure ────────────────────────────────────────────────

class _FakeEnforcer:
    async def enforce(self, *a, **kw): pass
    async def run_with_timeout(self, callable_obj, coro, *a, **kw):
        return await coro
    async def check_output_size(self, *a, **kw): pass


class _FakeEmitter:
    def emit(self, *a, **kw): pass


class _FakeTracer:
    def record(self, *a, **kw): pass


def _make(ToolClass):
    return ToolClass(_FakeEnforcer(), _FakeEmitter(), _FakeTracer())


def _ctx():
    ctx = MagicMock()
    ctx.run_id = "test-run"
    ctx.child.return_value = ctx
    ctx.register_cleanup = MagicMock()
    ctx.run_cleanups = MagicMock()
    return ctx


# ── Registration ──────────────────────────────────────────────────────────────

def test_all_security_tools_registered():
    names = [t.name for t in ALL_SECURITY_TOOLS]
    assert "port_scanner" in names
    assert "network_recon" in names
    assert "os_fingerprint" in names
    assert "hypervisor_detect" in names
    assert "kernel_audit" in names
    assert "ssl_tls_audit" in names
    assert "vuln_scanner" in names
    assert "network_vuln_scan" in names
    assert "process_inspector" in names
    assert "user_audit" in names
    assert "firewall_inspect" in names
    assert "dns_recon" in names
    assert "hash_integrity" in names
    assert "secrets_scanner" in names
    assert len(ALL_SECURITY_TOOLS) == 14


def test_all_tools_have_approval_for_network_tools():
    from citnega.packages.tools.security import (
        DNSReconTool, NetworkReconTool, NetworkVulnScanTool, PortScannerTool, SSLTLSAuditTool,
    )
    for cls in (PortScannerTool, NetworkReconTool, NetworkVulnScanTool, SSLTLSAuditTool, DNSReconTool):
        assert cls.policy.requires_approval, f"{cls.name} should require approval"
        assert cls.policy.network_allowed, f"{cls.name} should have network_allowed"


# ── VulnScanner (static, no I/O) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vuln_scanner_detects_hardcoded_password(tmp_path):
    from citnega.packages.tools.security.vuln_scanner import VulnScannerInput, VulnScannerTool

    code = tmp_path / "app.py"
    code.write_text('db_password = "supersecret123"\n')

    tool = _make(VulnScannerTool)
    result = await tool._execute(VulnScannerInput(path=str(tmp_path)), _ctx())

    assert result.total_findings >= 1
    cats = [f.category for f in result.findings]
    assert any("Credential" in c or "Password" in c for c in cats)


@pytest.mark.asyncio
async def test_vuln_scanner_detects_sql_injection(tmp_path):
    from citnega.packages.tools.security.vuln_scanner import VulnScannerInput, VulnScannerTool

    code = tmp_path / "db.py"
    code.write_text('cursor.execute("SELECT * FROM users WHERE id = " + user_id)\n')

    tool = _make(VulnScannerTool)
    result = await tool._execute(VulnScannerInput(path=str(tmp_path)), _ctx())

    sql_findings = [f for f in result.findings if "SQL" in f.category]
    assert sql_findings, "Should detect SQL injection"
    assert sql_findings[0].severity == "critical"


@pytest.mark.asyncio
async def test_vuln_scanner_detects_eval(tmp_path):
    from citnega.packages.tools.security.vuln_scanner import VulnScannerInput, VulnScannerTool

    code = tmp_path / "run.py"
    code.write_text("result = eval(user_input)\n")

    tool = _make(VulnScannerTool)
    result = await tool._execute(VulnScannerInput(path=str(tmp_path)), _ctx())

    assert any("Injection" in f.category for f in result.findings)


@pytest.mark.asyncio
async def test_vuln_scanner_clean_file_no_findings(tmp_path):
    from citnega.packages.tools.security.vuln_scanner import VulnScannerInput, VulnScannerTool

    code = tmp_path / "clean.py"
    code.write_text("def add(a, b):\n    return a + b\n")

    tool = _make(VulnScannerTool)
    result = await tool._execute(VulnScannerInput(path=str(tmp_path)), _ctx())
    assert result.total_findings == 0


# ── SecretsScanner ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_secrets_scanner_finds_aws_key(tmp_path):
    from citnega.packages.tools.security.secrets_scanner import SecretsScannerInput, SecretsScannerTool

    f = tmp_path / "config.py"
    f.write_text('AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

    tool = _make(SecretsScannerTool)
    result = await tool._execute(SecretsScannerInput(path=str(tmp_path)), _ctx())

    assert result.critical >= 1
    assert any("AWS" in f.secret_type for f in result.findings)


@pytest.mark.asyncio
async def test_secrets_scanner_finds_pem_key(tmp_path):
    from citnega.packages.tools.security.secrets_scanner import SecretsScannerInput, SecretsScannerTool

    f = tmp_path / "key.pem"
    f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEo...\n")

    tool = _make(SecretsScannerTool)
    result = await tool._execute(
        SecretsScannerInput(path=str(tmp_path), extensions=[".pem", ".py"]), _ctx()
    )

    assert any("Private Key" in f.secret_type for f in result.findings)


@pytest.mark.asyncio
async def test_secrets_scanner_redacts_snippets(tmp_path):
    from citnega.packages.tools.security.secrets_scanner import SecretsScannerInput, SecretsScannerTool

    f = tmp_path / "conf.py"
    # Build the token at runtime so the repo does not contain raw secret-like literals.
    secret = "sk_live_" + "abcdefghijklmnopqrstuvwx"
    f.write_text(f'STRIPE_SECRET = "{secret}"\n')

    tool = _make(SecretsScannerTool)
    result = await tool._execute(SecretsScannerInput(path=str(tmp_path)), _ctx())

    for finding in result.findings:
        assert secret not in finding.snippet, \
            "Full secret must be redacted in snippet"


# ── OSFingerprint (local, no network) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_os_fingerprint_returns_current_os():
    from citnega.packages.tools.security.os_fingerprint import OSFingerprintInput, OSFingerprintTool

    tool = _make(OSFingerprintTool)
    result = await tool._execute(OSFingerprintInput(), _ctx())

    assert result.os_name == platform.system()
    assert result.architecture
    assert result.hostname


# ── HypervisorDetect ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hypervisor_detect_returns_result():
    from citnega.packages.tools.security.hypervisor_detect import HypervisorDetectInput, HypervisorDetectTool

    tool = _make(HypervisorDetectTool)
    result = await tool._execute(HypervisorDetectInput(), _ctx())

    assert isinstance(result.hypervisor, str)
    assert result.confidence in ("high", "medium", "low")
    assert isinstance(result.is_container, bool)


# ── KernelAudit ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kernel_audit_runs_on_any_platform():
    from citnega.packages.tools.security.kernel_audit import KernelAuditInput, KernelAuditTool

    tool = _make(KernelAuditTool)
    result = await tool._execute(KernelAuditInput(), _ctx())

    assert isinstance(result.kernel_version, str)
    # On non-Linux it returns gracefully with empty checks
    assert isinstance(result.checks, list)
    assert 0 <= result.overall_score <= 100


# ── FirewallInspect ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_firewall_inspect_returns_posture():
    from citnega.packages.tools.security.firewall_inspect import FirewallInspectInput, FirewallInspectTool

    tool = _make(FirewallInspectTool)
    result = await tool._execute(FirewallInspectInput(), _ctx())

    assert result.overall_posture in ("strict", "moderate", "permissive", "unknown")
    assert isinstance(result.findings, list)


# ── HashIntegrity ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hash_integrity_single_file(tmp_path):
    from citnega.packages.tools.security.hash_integrity import HashIntegrityInput, HashIntegrityTool

    f = tmp_path / "test.txt"
    f.write_text("hello world")

    tool = _make(HashIntegrityTool)
    result = await tool._execute(HashIntegrityInput(path=str(f)), _ctx())

    assert result.total_files == 1
    assert len(result.entries[0].hash) == 64  # sha256 hex


@pytest.mark.asyncio
async def test_hash_integrity_baseline_roundtrip(tmp_path):
    from citnega.packages.tools.security.hash_integrity import HashIntegrityInput, HashIntegrityTool

    f = tmp_path / "data.txt"
    f.write_text("original")
    baseline = tmp_path / "baseline.json"

    tool = _make(HashIntegrityTool)
    # Create baseline
    await tool._execute(
        HashIntegrityInput(path=str(tmp_path), save_baseline_to=str(baseline)), _ctx()
    )
    assert baseline.exists()

    # No changes — should show 0 modified
    result = await tool._execute(
        HashIntegrityInput(path=str(tmp_path), baseline_file=str(baseline)), _ctx()
    )
    assert result.baseline_diff is not None
    assert result.baseline_diff.modified == []

    # Modify and re-check
    f.write_text("changed content")
    result2 = await tool._execute(
        HashIntegrityInput(path=str(tmp_path), baseline_file=str(baseline)), _ctx()
    )
    assert str(f) in result2.baseline_diff.modified


# ── ProcessInspector ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_inspector_lists_processes():
    from citnega.packages.tools.security.process_inspector import ProcessInspectorInput, ProcessInspectorTool

    try:
        import psutil  # noqa: F401
        has_psutil = True
    except ImportError:
        has_psutil = False

    tool = _make(ProcessInspectorTool)
    result = await tool._execute(ProcessInspectorInput(include_connections=False), _ctx())

    if has_psutil or platform.system() == "Linux":
        assert result.total_processes > 0
        import os
        our_pid = os.getpid()
        pids = [p.pid for p in result.processes]
        assert our_pid in pids
    else:
        # psutil not installed and not Linux — result may be empty, just check it's valid
        assert isinstance(result.processes, list)


# ── UserAudit ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_audit_basic(tmp_path):
    from citnega.packages.tools.security.user_audit import UserAuditInput, UserAuditTool

    tool = _make(UserAuditTool)
    result = await tool._execute(
        UserAuditInput(scan_suid=False, scan_ssh_keys=False, scan_crontabs=False),
        _ctx(),
    )

    if platform.system() in ("Linux", "Darwin"):
        assert len(result.users) > 0


# ── DNSRecon (mocked network) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dns_recon_no_network(monkeypatch):
    from citnega.packages.tools.security import dns_recon as dr_mod
    from citnega.packages.tools.security.dns_recon import DNSReconInput, DNSReconTool

    # Stub out subprocess and socket calls
    monkeypatch.setattr(dr_mod, "_dig", lambda *a, **kw: [])
    monkeypatch.setattr(dr_mod, "_check_wildcard", lambda d: False)
    monkeypatch.setattr(dr_mod, "_dnssec_check", lambda d: False)

    tool = _make(DNSReconTool)
    result = await tool._execute(
        DNSReconInput(domain="example.com", attempt_zone_transfer=False, enumerate_subdomains=False),
        _ctx(),
    )

    assert result.domain == "example.com"
    assert isinstance(result.findings, list)


# ── PortScanner (mocked network) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_port_scanner_no_network(monkeypatch):
    from citnega.packages.tools.security import port_scanner as ps_mod
    from citnega.packages.tools.security.port_scanner import PortScannerInput, PortScannerTool

    async def _fake_probe(host, port, timeout, grab):
        from citnega.packages.tools.security.port_scanner import PortResult
        return PortResult(port=port, protocol="tcp", state="closed", service="unknown", banner="")

    monkeypatch.setattr(ps_mod, "_tcp_probe", _fake_probe)
    monkeypatch.setattr("socket.gethostbyname", lambda h: "127.0.0.1")

    tool = _make(PortScannerTool)
    result = await tool._execute(
        PortScannerInput(target="127.0.0.1", ports="80,443", grab_banner=False),
        _ctx(),
    )

    assert result.target == "127.0.0.1"
    assert result.total_scanned == 2
    assert result.open_ports == []


# ── SSLTLSAudit (mocked) ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ssl_tls_audit_connection_failure():
    from citnega.packages.tools.security.ssl_tls_audit import SSLTLSAuditInput, SSLTLSAuditTool

    tool = _make(SSLTLSAuditTool)
    # 192.0.2.1 is TEST-NET — guaranteed unreachable
    result = await tool._execute(
        SSLTLSAuditInput(host="192.0.2.1", port=443, timeout=1.0),
        _ctx(),
    )

    # Should return gracefully with empty cert and warnings
    assert isinstance(result.findings, list)
    assert result.host == "192.0.2.1"
