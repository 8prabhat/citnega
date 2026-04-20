"""Security tools — authorized penetration testing and defensive security."""

from citnega.packages.tools.security.dns_recon import DNSReconTool
from citnega.packages.tools.security.firewall_inspect import FirewallInspectTool
from citnega.packages.tools.security.hash_integrity import HashIntegrityTool
from citnega.packages.tools.security.hypervisor_detect import HypervisorDetectTool
from citnega.packages.tools.security.kernel_audit import KernelAuditTool
from citnega.packages.tools.security.network_recon import NetworkReconTool
from citnega.packages.tools.security.network_vuln_scan import NetworkVulnScanTool
from citnega.packages.tools.security.os_fingerprint import OSFingerprintTool
from citnega.packages.tools.security.port_scanner import PortScannerTool
from citnega.packages.tools.security.process_inspector import ProcessInspectorTool
from citnega.packages.tools.security.secrets_scanner import SecretsScannerTool
from citnega.packages.tools.security.ssl_tls_audit import SSLTLSAuditTool
from citnega.packages.tools.security.user_audit import UserAuditTool
from citnega.packages.tools.security.vuln_scanner import VulnScannerTool

ALL_SECURITY_TOOLS = [
    PortScannerTool,
    NetworkReconTool,
    OSFingerprintTool,
    HypervisorDetectTool,
    KernelAuditTool,
    SSLTLSAuditTool,
    VulnScannerTool,
    NetworkVulnScanTool,
    ProcessInspectorTool,
    UserAuditTool,
    FirewallInspectTool,
    DNSReconTool,
    HashIntegrityTool,
    SecretsScannerTool,
]

__all__ = [
    "ALL_SECURITY_TOOLS",
    "DNSReconTool",
    "FirewallInspectTool",
    "HashIntegrityTool",
    "HypervisorDetectTool",
    "KernelAuditTool",
    "NetworkReconTool",
    "NetworkVulnScanTool",
    "OSFingerprintTool",
    "PortScannerTool",
    "ProcessInspectorTool",
    "SecretsScannerTool",
    "SSLTLSAuditTool",
    "UserAuditTool",
    "VulnScannerTool",
]
