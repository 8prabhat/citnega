"""Built-in tools — v1 set."""

from citnega.packages.tools.builtin.artifact_pack import ArtifactPackTool
from citnega.packages.tools.builtin.diff_tool import DiffTool
from citnega.packages.tools.builtin.env_inspector_tool import EnvInspectorTool
from citnega.packages.tools.builtin.fetch_url import FetchURLTool
from citnega.packages.tools.builtin.git_log_tool import GitLogTool
from citnega.packages.tools.builtin.json_query_tool import JSONQueryTool
from citnega.packages.tools.builtin.list_dir import ListDirTool
from citnega.packages.tools.builtin.quality_gate import QualityGateTool
from citnega.packages.tools.builtin.read_file import ReadFileTool
from citnega.packages.tools.builtin.read_kb import ReadKBTool
from citnega.packages.tools.builtin.repo_map import RepoMapTool
from citnega.packages.tools.builtin.run_shell import RunShellTool
from citnega.packages.tools.builtin.search_files import SearchFilesTool
from citnega.packages.tools.builtin.search_web import SearchWebTool
from citnega.packages.tools.builtin.summarize_text import SummarizeTextTool
from citnega.packages.tools.builtin.test_matrix import MatrixTool
from citnega.packages.tools.builtin.write_file import WriteFileTool
from citnega.packages.tools.builtin.write_kb import WriteKBTool

ALL_TOOLS = [
    ReadFileTool,
    WriteFileTool,
    ListDirTool,
    SearchFilesTool,
    RunShellTool,
    RepoMapTool,
    QualityGateTool,
    MatrixTool,
    ArtifactPackTool,
    FetchURLTool,
    SearchWebTool,
    ReadKBTool,
    WriteKBTool,
    SummarizeTextTool,
    DiffTool,
    JSONQueryTool,
    GitLogTool,
    EnvInspectorTool,
]

__all__ = [
    "ALL_TOOLS",
    "ArtifactPackTool",
    "DiffTool",
    "EnvInspectorTool",
    "FetchURLTool",
    "GitLogTool",
    "JSONQueryTool",
    "ListDirTool",
    "MatrixTool",
    "QualityGateTool",
    "ReadFileTool",
    "ReadKBTool",
    "RepoMapTool",
    "RunShellTool",
    "SearchFilesTool",
    "SearchWebTool",
    "SummarizeTextTool",
    "WriteFileTool",
    "WriteKBTool",
]
