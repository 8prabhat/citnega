"""jira_ops — Jira REST API: create, read, update, search issues."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class JiraOpsInput(BaseModel):
    operation: str = Field(description="Operation: 'create' | 'get' | 'update' | 'search'")
    issue_key: str = Field(default="", description="Issue key (e.g. PROJ-123) for get/update.")
    project_key: str = Field(default="", description="Project key for create.")
    summary: str = Field(default="", description="Issue summary for create/update.")
    description: str = Field(default="", description="Issue description.")
    issue_type: str = Field(default="Task", description="Issue type: Task, Bug, Story, Epic.")
    status: str = Field(default="", description="Transition status for update.")
    jql: str = Field(default="", description="JQL query for search.")
    fields: dict = Field(default_factory=dict, description="Additional fields for create/update.")
    max_results: int = Field(default=20)


class JiraOpsTool(BaseCallable):
    name = "jira_ops"
    description = (
        "Jira REST API integration: create issues, get issue details, update status/fields, "
        "and search with JQL. Requires JIRA_URL and JIRA_TOKEN environment variables."
    )
    callable_type = CallableType.TOOL
    input_schema = JiraOpsInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: JiraOpsInput, context: CallContext) -> ToolOutput:
        jira_url = os.environ.get("JIRA_URL", "").rstrip("/")
        jira_token = os.environ.get("JIRA_TOKEN", "")
        if not jira_url or not jira_token:
            return ToolOutput(result="[jira_ops: JIRA_URL and JIRA_TOKEN env vars required]")

        try:
            import httpx
        except ImportError:
            return ToolOutput(result="[jira_ops: httpx not installed — run: pip install httpx]")

        headers = {
            "Authorization": f"Bearer {jira_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                if input.operation == "get":
                    if not input.issue_key:
                        return ToolOutput(result="[jira_ops: issue_key required for get]")
                    resp = await client.get(f"{jira_url}/rest/api/3/issue/{input.issue_key}", headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    fields = data.get("fields", {})
                    return ToolOutput(result=(
                        f"Key: {data['key']}\n"
                        f"Summary: {fields.get('summary', '')}\n"
                        f"Status: {fields.get('status', {}).get('name', '')}\n"
                        f"Type: {fields.get('issuetype', {}).get('name', '')}\n"
                        f"Assignee: {(fields.get('assignee') or {}).get('displayName', 'Unassigned')}\n"
                        f"Description: {str(fields.get('description', ''))[:500]}"
                    ))

                elif input.operation == "create":
                    if not input.project_key or not input.summary:
                        return ToolOutput(result="[jira_ops: project_key and summary required for create]")
                    payload: dict = {
                        "fields": {
                            "project": {"key": input.project_key},
                            "summary": input.summary,
                            "issuetype": {"name": input.issue_type},
                            **input.fields,
                        }
                    }
                    if input.description:
                        payload["fields"]["description"] = {
                            "type": "doc", "version": 1,
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": input.description}]}],
                        }
                    resp = await client.post(f"{jira_url}/rest/api/3/issue", headers=headers, json=payload)
                    resp.raise_for_status()
                    key = resp.json().get("key", "?")
                    return ToolOutput(result=f"Created: {key} — {jira_url}/browse/{key}")

                elif input.operation == "update":
                    if not input.issue_key:
                        return ToolOutput(result="[jira_ops: issue_key required for update]")
                    update_fields: dict = {**input.fields}
                    if input.summary:
                        update_fields["summary"] = input.summary
                    if update_fields:
                        resp = await client.put(
                            f"{jira_url}/rest/api/3/issue/{input.issue_key}",
                            headers=headers, json={"fields": update_fields},
                        )
                        resp.raise_for_status()
                    if input.status:
                        trans_resp = await client.get(
                            f"{jira_url}/rest/api/3/issue/{input.issue_key}/transitions",
                            headers=headers,
                        )
                        trans_resp.raise_for_status()
                        transitions = trans_resp.json().get("transitions", [])
                        tid = next((t["id"] for t in transitions if t["name"].lower() == input.status.lower()), None)
                        if tid:
                            await client.post(
                                f"{jira_url}/rest/api/3/issue/{input.issue_key}/transitions",
                                headers=headers, json={"transition": {"id": tid}},
                            )
                    return ToolOutput(result=f"Updated: {input.issue_key}")

                elif input.operation == "search":
                    jql = input.jql or f"project is not EMPTY ORDER BY updated DESC"
                    resp = await client.get(
                        f"{jira_url}/rest/api/3/search",
                        headers=headers,
                        params={"jql": jql, "maxResults": input.max_results, "fields": "summary,status,issuetype,assignee"},
                    )
                    resp.raise_for_status()
                    issues = resp.json().get("issues", [])
                    lines = [f"Found {len(issues)} issues:"]
                    for iss in issues:
                        f = iss.get("fields", {})
                        lines.append(
                            f"  {iss['key']} [{f.get('issuetype', {}).get('name', '?')}] "
                            f"{f.get('status', {}).get('name', '?')}: {f.get('summary', '')[:80]}"
                        )
                    return ToolOutput(result="\n".join(lines))

                else:
                    return ToolOutput(result=f"[jira_ops: unknown operation '{input.operation}']")

        except Exception as exc:
            return ToolOutput(result=f"[jira_ops: {exc}]")
