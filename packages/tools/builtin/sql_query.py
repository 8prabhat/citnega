"""sql_query — run a read-only SQL SELECT against a SQLite database file."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_FORBIDDEN_KEYWORDS = {"insert", "update", "delete", "drop", "create", "alter", "replace", "truncate", "attach"}


def _is_read_only(query: str) -> bool:
    first_word = query.strip().split()[0].lower() if query.strip() else ""
    return first_word == "select" and not any(kw in query.lower() for kw in _FORBIDDEN_KEYWORDS)


class SQLQueryInput(BaseModel):
    db_path: str = Field(description="Path to the SQLite database file.")
    query: str = Field(description="SQL SELECT query to execute.")
    params: list[Any] = Field(default_factory=list, description="Positional query parameters (? placeholders).")
    max_rows: int = Field(default=100, description="Maximum rows to return.")
    output_format: str = Field(default="markdown", description="Output format: markdown | json | csv")


class SQLQueryTool(BaseCallable):
    """Run a read-only SQL SELECT query against a SQLite database file."""

    name = "sql_query"
    description = (
        "Execute a read-only SQL SELECT query against a SQLite (.db/.sqlite) file. "
        "Only SELECT statements are permitted — no INSERT/UPDATE/DELETE/DDL. "
        "Returns results as markdown table, JSON, or CSV. Also supports "
        "SELECT name FROM sqlite_master WHERE type='table' to list tables."
    )
    callable_type = CallableType.TOOL
    input_schema = SQLQueryInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: SQLQueryInput, context: CallContext) -> ToolOutput:
        path = Path(input.db_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[sql_query: database not found: {path}]")

        if not _is_read_only(input.query):
            return ToolOutput(result="[sql_query: only SELECT queries are permitted]")

        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(input.query, input.params)
            rows = cur.fetchmany(input.max_rows)
            col_names = [d[0] for d in cur.description] if cur.description else []
            total = len(rows)
            conn.close()
        except Exception as exc:
            return ToolOutput(result=f"[sql_query: query error: {exc}]")

        if not rows:
            return ToolOutput(result="Query returned 0 rows.")

        data = [dict(zip(col_names, row)) for row in rows]
        fmt = input.output_format.lower()

        if fmt == "json":
            import json
            return ToolOutput(result=f"{total} row(s)\n{json.dumps(data, default=str, indent=2)}")

        if fmt == "csv":
            import csv, io
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(data)
            return ToolOutput(result=f"{total} row(s)\n{buf.getvalue()}")

        # Default: markdown table
        header = " | ".join(col_names)
        sep = " | ".join(["---"] * len(col_names))
        body_rows = [" | ".join(str(r.get(c, "")) for c in col_names) for r in data]
        truncation = f"\n_(showing {total} of potentially more rows — increase max_rows to see more)_" if total == input.max_rows else ""
        return ToolOutput(result=f"{total} row(s)\n\n| {header} |\n| {sep} |\n" + "\n".join(f"| {r} |" for r in body_rows) + truncation)
