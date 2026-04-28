"""linear_ops — Linear project management: issues, cycles, and teams via GraphQL."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_LINEAR_GQL = "https://api.linear.app/graphql"


class LinearOpsInput(BaseModel):
    operation: str = Field(
        description="Operation: 'create_issue' | 'update_issue' | 'list_issues' | 'create_cycle' | 'add_to_cycle'"
    )
    title: str = Field(default="", description="Issue title for create/update.")
    description: str = Field(default="", description="Issue description (markdown).")
    team_id: str = Field(default="", description="Team ID for issue creation.")
    issue_id: str = Field(default="", description="Issue ID for update/add_to_cycle.")
    status: str = Field(default="", description="Status name for update (e.g. 'In Progress', 'Done').")
    priority: int = Field(default=0, description="Priority 0=no priority, 1=urgent, 2=high, 3=medium, 4=low.")
    cycle_id: str = Field(default="", description="Cycle ID for add_to_cycle.")
    issue_ids: list[str] = Field(default_factory=list, description="Issue IDs for bulk add_to_cycle.")
    max_results: int = Field(default=20)


class LinearOpsTool(BaseCallable):
    name = "linear_ops"
    description = (
        "Linear project management: create/update issues, list issues, manage cycles. "
        "Requires LINEAR_API_KEY environment variable."
    )
    callable_type = CallableType.TOOL
    input_schema = LinearOpsInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: LinearOpsInput, context: CallContext) -> ToolOutput:
        api_key = os.environ.get("LINEAR_API_KEY", "")
        if not api_key:
            return ToolOutput(result="[linear_ops: LINEAR_API_KEY env var required]")

        try:
            import httpx
        except ImportError:
            return ToolOutput(result="[linear_ops: httpx not installed — run: pip install httpx]")

        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                return await self._dispatch(client, headers, input)
        except Exception as exc:
            return ToolOutput(result=f"[linear_ops: {exc}]")

    async def _dispatch(self, client, headers: dict, input: LinearOpsInput) -> ToolOutput:
        import httpx

        async def gql(query: str, variables: dict) -> dict:
            resp = await client.post(_LINEAR_GQL, headers=headers, json={"query": query, "variables": variables})
            resp.raise_for_status()
            return resp.json()

        if input.operation == "create_issue":
            if not input.title or not input.team_id:
                return ToolOutput(result="[linear_ops: title and team_id required for create_issue]")
            mutation = """
            mutation CreateIssue($title: String!, $description: String, $teamId: String!, $priority: Int) {
                issueCreate(input: {title: $title, description: $description, teamId: $teamId, priority: $priority}) {
                    success
                    issue { id identifier url title }
                }
            }"""
            data = await gql(mutation, {
                "title": input.title,
                "description": input.description or None,
                "teamId": input.team_id,
                "priority": input.priority,
            })
            issue = data.get("data", {}).get("issueCreate", {}).get("issue", {})
            if not issue:
                return ToolOutput(result=f"[linear_ops: create_issue failed — {data.get('errors')}]")
            return ToolOutput(result=f"Created: {issue['identifier']} — {issue['url']}\nTitle: {issue['title']}")

        elif input.operation == "update_issue":
            if not input.issue_id:
                return ToolOutput(result="[linear_ops: issue_id required for update_issue]")
            updates: dict = {}
            if input.title:
                updates["title"] = input.title
            if input.description:
                updates["description"] = input.description
            if input.priority:
                updates["priority"] = input.priority
            if not updates and not input.status:
                return ToolOutput(result="[linear_ops: nothing to update — provide title, description, priority, or status]")

            if input.status:
                state_q = """query States($filter: WorkflowStateFilter) {
                    workflowStates(filter: $filter) { nodes { id name } }
                }"""
                state_data = await gql(state_q, {"filter": {"name": {"eq": input.status}}})
                nodes = state_data.get("data", {}).get("workflowStates", {}).get("nodes", [])
                if nodes:
                    updates["stateId"] = nodes[0]["id"]

            mutation = """
            mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
                issueUpdate(id: $id, input: $input) {
                    success
                    issue { identifier url }
                }
            }"""
            data = await gql(mutation, {"id": input.issue_id, "input": updates})
            issue = data.get("data", {}).get("issueUpdate", {}).get("issue", {})
            return ToolOutput(result=f"Updated: {issue.get('identifier', input.issue_id)} — {issue.get('url', '')}")

        elif input.operation == "list_issues":
            query = """
            query ListIssues($first: Int) {
                issues(first: $first, orderBy: updatedAt) {
                    nodes { identifier title state { name } priority assignee { name } url }
                }
            }"""
            data = await gql(query, {"first": input.max_results})
            issues = data.get("data", {}).get("issues", {}).get("nodes", [])
            if not issues:
                return ToolOutput(result="[linear_ops: no issues found]")
            lines = [f"Issues ({len(issues)}):"]
            for iss in issues:
                p = ["", "urgent", "high", "medium", "low"][iss.get("priority", 0)] or "none"
                lines.append(
                    f"  {iss['identifier']} [{iss.get('state', {}).get('name', '?')}] "
                    f"[{p}] {iss['title'][:70]}"
                )
            return ToolOutput(result="\n".join(lines))

        elif input.operation == "create_cycle":
            if not input.team_id or not input.title:
                return ToolOutput(result="[linear_ops: team_id and title required for create_cycle]")
            mutation = """
            mutation CreateCycle($teamId: String!, $name: String!) {
                cycleCreate(input: {teamId: $teamId, name: $name}) {
                    success
                    cycle { id name }
                }
            }"""
            data = await gql(mutation, {"teamId": input.team_id, "name": input.title})
            cycle = data.get("data", {}).get("cycleCreate", {}).get("cycle", {})
            return ToolOutput(result=f"Created cycle: {cycle.get('name')} (id: {cycle.get('id')})")

        elif input.operation == "add_to_cycle":
            ids = input.issue_ids or ([input.issue_id] if input.issue_id else [])
            if not ids or not input.cycle_id:
                return ToolOutput(result="[linear_ops: cycle_id and issue_id(s) required for add_to_cycle]")
            mutation = """
            mutation AddIssuesToCycle($id: String!, $issueIds: [String!]!) {
                cycleUpdate(id: $id, input: {}) { success }
                issueUpdate(id: $issueIds[0], input: {cycleId: $id}) { success }
            }"""
            mutation = """
            mutation AddToCycle($issueId: String!, $cycleId: String!) {
                issueUpdate(id: $issueId, input: {cycleId: $cycleId}) { success issue { identifier } }
            }"""
            results = []
            for iid in ids:
                data = await gql(mutation, {"issueId": iid, "cycleId": input.cycle_id})
                iss = data.get("data", {}).get("issueUpdate", {}).get("issue", {})
                results.append(iss.get("identifier", iid))
            return ToolOutput(result=f"Added to cycle {input.cycle_id}: {', '.join(results)}")

        else:
            return ToolOutput(result=f"[linear_ops: unknown operation '{input.operation}']")
