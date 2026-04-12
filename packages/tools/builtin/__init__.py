"""Built-in tools — v1 set."""

from citnega.packages.tools.builtin.fetch_url import FetchURLTool
from citnega.packages.tools.builtin.list_dir import ListDirTool
from citnega.packages.tools.builtin.read_file import ReadFileTool
from citnega.packages.tools.builtin.read_kb import ReadKBTool
from citnega.packages.tools.builtin.run_shell import RunShellTool
from citnega.packages.tools.builtin.search_files import SearchFilesTool
from citnega.packages.tools.builtin.search_web import SearchWebTool
from citnega.packages.tools.builtin.summarize_text import SummarizeTextTool
from citnega.packages.tools.builtin.write_file import WriteFileTool
from citnega.packages.tools.builtin.write_kb import WriteKBTool

ALL_TOOLS = [
    ReadFileTool,
    WriteFileTool,
    ListDirTool,
    SearchFilesTool,
    RunShellTool,
    FetchURLTool,
    SearchWebTool,
    ReadKBTool,
    WriteKBTool,
    SummarizeTextTool,
]

__all__ = [
    "ALL_TOOLS",
    "FetchURLTool",
    "ListDirTool",
    "ReadFileTool",
    "ReadKBTool",
    "RunShellTool",
    "SearchFilesTool",
    "SearchWebTool",
    "SummarizeTextTool",
    "WriteFileTool",
    "WriteKBTool",
]
