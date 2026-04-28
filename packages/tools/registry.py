"""
ToolRegistry — factory that creates and returns all registered tool instances.

Usage in bootstrap::

    registry = ToolRegistry(
        enforcer=policy_enforcer,
        emitter=event_emitter,
        tracer=tracer,
        kb_store=kb_store,          # optional — for read_kb tool
    )
    tools: dict[str, IInvocable] = registry.build_all()

Following DIP: bootstrap code depends on this abstraction, not on concrete
tool imports scattered across files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.execution_backend import IExecutionBackend
    from citnega.packages.protocol.interfaces.knowledge_store import IKnowledgeStore
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer
    from citnega.packages.storage.path_resolver import PathResolver


class ToolRegistry:
    """
    Single source of truth for built-in tool instantiation.

    All tools receive the same injected infrastructure (enforcer, emitter,
    tracer).  Adding a new tool means adding it here and nowhere else (OCP).
    """

    def __init__(
        self,
        enforcer: IPolicyEnforcer,
        emitter: IEventEmitter,
        tracer: ITracer,
        path_resolver: PathResolver | None = None,
        kb_store: IKnowledgeStore | None = None,
        execution_backend: IExecutionBackend | None = None,
    ) -> None:
        self._enforcer = enforcer
        self._emitter = emitter
        self._tracer = tracer
        self._path_resolver = path_resolver
        self._kb_store = kb_store
        self._execution_backend = execution_backend

    def build_all(self) -> dict[str, IInvocable]:
        """Instantiate every built-in tool and return as name→instance dict."""
        tools: dict[str, IInvocable] = {}
        for tool in self._create_tools():
            tools[tool.name] = tool
        return tools

    # ── Private: create one instance per tool ────────────────────────────────

    def _deps(self):
        """Return the three common constructor args."""
        return self._enforcer, self._emitter, self._tracer

    def _create_tools(self) -> list[IInvocable]:
        from citnega.packages.tools.builtin.artifact_pack import ArtifactPackTool
        from citnega.packages.tools.builtin.calculate import CalculateTool
        from citnega.packages.tools.builtin.edit_file import EditFileTool
        from citnega.packages.tools.builtin.fetch_url import FetchURLTool
        from citnega.packages.tools.builtin.get_datetime import GetDatetimeTool
        from citnega.packages.tools.builtin.git_ops import GitOpsTool
        from citnega.packages.tools.builtin.list_dir import ListDirTool
        from citnega.packages.tools.builtin.quality_gate import QualityGateTool
        from citnega.packages.tools.builtin.read_file import ReadFileTool
        from citnega.packages.tools.builtin.read_webpage import ReadWebpageTool
        from citnega.packages.tools.builtin.repo_map import RepoMapTool
        from citnega.packages.tools.builtin.run_shell import RunShellTool
        from citnega.packages.tools.builtin.search_files import SearchFilesTool
        from citnega.packages.tools.builtin.search_web import SearchWebTool
        from citnega.packages.tools.builtin.summarize_text import SummarizeTextTool
        from citnega.packages.tools.builtin.test_matrix import MatrixTool
        from citnega.packages.tools.builtin.write_file import WriteFileTool

        instances: list[IInvocable] = [
            # ── Utilities ─────────────────────────────────────────────────────
            GetDatetimeTool(*self._deps()),
            CalculateTool(*self._deps()),
            # ── Filesystem ────────────────────────────────────────────────────
            ReadFileTool(*self._deps()),
            WriteFileTool(*self._deps()),
            EditFileTool(*self._deps()),
            ListDirTool(*self._deps()),
            SearchFilesTool(*self._deps()),
            # ── Execution & version control ───────────────────────────────────
            RunShellTool(*self._deps(), execution_backend=self._execution_backend),
            GitOpsTool(*self._deps()),
            # ── QA / architecture introspection ──────────────────────────────
            RepoMapTool(*self._deps()),
            QualityGateTool(*self._deps()),
            MatrixTool(*self._deps()),
            ArtifactPackTool(*self._deps(), path_resolver=self._path_resolver),
            # ── Web ───────────────────────────────────────────────────────────
            FetchURLTool(*self._deps()),
            SearchWebTool(*self._deps()),
            ReadWebpageTool(*self._deps()),
            # ── Text processing ───────────────────────────────────────────────
            SummarizeTextTool(*self._deps()),
        ]

        # KB tools require a live store
        if self._kb_store is not None:
            from citnega.packages.tools.builtin.read_kb import ReadKBTool
            from citnega.packages.tools.builtin.write_kb import WriteKBTool

            instances.append(ReadKBTool(*self._deps(), knowledge_store=self._kb_store))
            instances.append(WriteKBTool(*self._deps(), knowledge_store=self._kb_store))

        # ── Document output tools ─────────────────────────────────────────────
        from citnega.packages.tools.builtin.create_excel import CreateExcelTool
        from citnega.packages.tools.builtin.create_ppt import CreatePPTTool
        from citnega.packages.tools.builtin.render_chart import RenderChartTool
        from citnega.packages.tools.builtin.write_docx import WriteDocxTool
        from citnega.packages.tools.builtin.write_pdf import WritePDFTool

        instances += [
            WritePDFTool(*self._deps()),
            WriteDocxTool(*self._deps()),
            CreatePPTTool(*self._deps()),
            CreateExcelTool(*self._deps()),
            RenderChartTool(*self._deps()),
        ]

        # ── Communication tools ───────────────────────────────────────────────
        from citnega.packages.tools.builtin.calendar_event import CalendarEventTool
        from citnega.packages.tools.builtin.email_composer import EmailComposerTool
        from citnega.packages.tools.builtin.slack_notifier import SlackNotifierTool

        instances += [
            EmailComposerTool(*self._deps()),
            SlackNotifierTool(*self._deps()),
            CalendarEventTool(*self._deps()),
        ]

        # ── Data analysis tools ───────────────────────────────────────────────
        from citnega.packages.tools.builtin.data_profiler import DataProfilerTool
        from citnega.packages.tools.builtin.pandas_analyze import PandasAnalyzeTool
        from citnega.packages.tools.builtin.pivot_table import PivotTableTool
        from citnega.packages.tools.builtin.sql_query import SQLQueryTool
        from citnega.packages.tools.builtin.web_scraper import WebScraperTool

        instances += [
            PandasAnalyzeTool(*self._deps()),
            SQLQueryTool(*self._deps()),
            DataProfilerTool(*self._deps()),
            PivotTableTool(*self._deps()),
            WebScraperTool(*self._deps()),
        ]

        # ── General utility tools ─────────────────────────────────────────────
        from citnega.packages.tools.builtin.csv_to_json import CSVToJSONTool
        from citnega.packages.tools.builtin.diff_compare import DiffCompareTool
        from citnega.packages.tools.builtin.ocr_image import OCRImageTool
        from citnega.packages.tools.builtin.qr_code import QRCodeTool
        from citnega.packages.tools.builtin.translate_text import TranslateTextTool

        instances += [
            TranslateTextTool(*self._deps()),
            OCRImageTool(*self._deps()),
            QRCodeTool(*self._deps()),
            DiffCompareTool(*self._deps()),
            CSVToJSONTool(*self._deps()),
        ]

        # ── Utility analysis tools ─────────────────────────────────────────────
        from citnega.packages.tools.builtin.api_tester import APITesterTool
        from citnega.packages.tools.builtin.dependency_auditor import DependencyAuditorTool
        from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerTool
        from citnega.packages.tools.builtin.memory_inspector import MemoryInspectorTool
        from citnega.packages.tools.builtin.perf_profiler import PerfProfilerTool

        instances += [
            MemoryInspectorTool(*self._deps()),
            LogAnalyzerTool(*self._deps()),
            APITesterTool(*self._deps()),
            DependencyAuditorTool(*self._deps()),
            PerfProfilerTool(*self._deps()),
        ]

        # Security tools (always registered; approval gates in policy)
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

        # ── Tier-1 integration tools ──────────────────────────────────────────
        from citnega.packages.tools.builtin.agent_delegate import AgentDelegateTool
        from citnega.packages.tools.builtin.browser_session import BrowserSessionTool
        from citnega.packages.tools.builtin.calendar_query import CalendarQueryTool
        from citnega.packages.tools.builtin.cloud_ops import CloudOpsTool
        from citnega.packages.tools.builtin.email_reader import EmailReaderTool
        from citnega.packages.tools.builtin.github_ops import GitHubOpsTool
        from citnega.packages.tools.builtin.jira_ops import JiraOpsTool
        from citnega.packages.tools.builtin.linear_ops import LinearOpsTool
        from citnega.packages.tools.builtin.mermaid_render import MermaidRenderTool
        from citnega.packages.tools.builtin.prometheus_query import PrometheusQueryTool
        from citnega.packages.tools.builtin.vault_secret import VaultSecretTool

        instances += [
            BrowserSessionTool(*self._deps()),
            MermaidRenderTool(*self._deps()),
            JiraOpsTool(*self._deps()),
            GitHubOpsTool(*self._deps()),
            VaultSecretTool(*self._deps()),
            CloudOpsTool(*self._deps()),
            EmailReaderTool(*self._deps()),
            CalendarQueryTool(*self._deps()),
            PrometheusQueryTool(*self._deps()),
            LinearOpsTool(*self._deps()),
            AgentDelegateTool(*self._deps()),
        ]

        instances += [
            # ── Security: passive / local ─────────────────────────────────────
            OSFingerprintTool(*self._deps()),
            HypervisorDetectTool(*self._deps()),
            KernelAuditTool(*self._deps()),
            ProcessInspectorTool(*self._deps()),
            UserAuditTool(*self._deps()),
            FirewallInspectTool(*self._deps()),
            HashIntegrityTool(*self._deps()),
            VulnScannerTool(*self._deps()),
            SecretsScannerTool(*self._deps()),
            # ── Security: network (approval required) ─────────────────────────
            PortScannerTool(*self._deps()),
            NetworkReconTool(*self._deps()),
            NetworkVulnScanTool(*self._deps()),
            SSLTLSAuditTool(*self._deps()),
            DNSReconTool(*self._deps()),
        ]

        return instances
