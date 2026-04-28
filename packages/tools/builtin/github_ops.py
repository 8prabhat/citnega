"""github_ops — GitHub REST API: PRs, issues, workflow triggers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_GH_API = "https://api.github.com"


class GitHubOpsInput(BaseModel):
    operation: str = Field(
        description="Operation: 'list_prs' | 'get_pr' | 'create_pr' | 'list_issues' | 'create_issue' | 'trigger_workflow'"
    )
    owner: str = Field(default="", description="Repository owner (user or org).")
    repo: str = Field(default="", description="Repository name.")
    number: int = Field(default=0, description="PR or issue number.")
    title: str = Field(default="", description="Title for create operations.")
    body: str = Field(default="", description="Body for create operations.")
    head: str = Field(default="", description="Head branch for create_pr.")
    base: str = Field(default="main", description="Base branch for create_pr.")
    workflow_id: str = Field(default="", description="Workflow filename for trigger_workflow.")
    ref: str = Field(default="main", description="Branch/tag ref for trigger_workflow.")
    state: str = Field(default="open", description="Filter state: open | closed | all.")
    labels: list[str] = Field(default_factory=list, description="Labels for create operations.")
    max_results: int = Field(default=20)


class GitHubOpsTool(BaseCallable):
    name = "github_ops"
    description = (
        "GitHub REST API: list/create/get PRs and issues, trigger GitHub Actions workflows. "
        "Requires GITHUB_TOKEN environment variable."
    )
    callable_type = CallableType.TOOL
    input_schema = GitHubOpsInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: GitHubOpsInput, context: CallContext) -> ToolOutput:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return ToolOutput(result="[github_ops: GITHUB_TOKEN env var required]")

        try:
            import httpx
        except ImportError:
            return ToolOutput(result="[github_ops: httpx not installed — run: pip install httpx]")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        def _repo_url() -> str:
            return f"{_GH_API}/repos/{input.owner}/{input.repo}"

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                if input.operation == "list_prs":
                    resp = await client.get(
                        f"{_repo_url()}/pulls",
                        headers=headers,
                        params={"state": input.state, "per_page": input.max_results},
                    )
                    resp.raise_for_status()
                    prs = resp.json()
                    lines = [f"PRs ({input.state}): {len(prs)} found"]
                    for pr in prs:
                        lines.append(f"  #{pr['number']} [{pr['state']}] {pr['title'][:70]} ({pr['user']['login']})")
                    return ToolOutput(result="\n".join(lines))

                elif input.operation == "get_pr":
                    resp = await client.get(f"{_repo_url()}/pulls/{input.number}", headers=headers)
                    resp.raise_for_status()
                    pr = resp.json()
                    return ToolOutput(result=(
                        f"PR #{pr['number']}: {pr['title']}\n"
                        f"State: {pr['state']} | Mergeable: {pr.get('mergeable')}\n"
                        f"Head: {pr['head']['label']} → Base: {pr['base']['label']}\n"
                        f"Author: {pr['user']['login']} | Reviews: {pr.get('review_comments', 0)}\n"
                        f"Body: {(pr.get('body') or '')[:500]}"
                    ))

                elif input.operation == "create_pr":
                    if not all([input.owner, input.repo, input.title, input.head]):
                        return ToolOutput(result="[github_ops: owner, repo, title, head required for create_pr]")
                    payload = {"title": input.title, "body": input.body, "head": input.head, "base": input.base}
                    resp = await client.post(f"{_repo_url()}/pulls", headers=headers, json=payload)
                    resp.raise_for_status()
                    pr = resp.json()
                    return ToolOutput(result=f"Created PR #{pr['number']}: {pr['html_url']}")

                elif input.operation == "list_issues":
                    resp = await client.get(
                        f"{_repo_url()}/issues",
                        headers=headers,
                        params={"state": input.state, "per_page": input.max_results},
                    )
                    resp.raise_for_status()
                    issues = [i for i in resp.json() if "pull_request" not in i]
                    lines = [f"Issues ({input.state}): {len(issues)} found"]
                    for iss in issues:
                        lines.append(f"  #{iss['number']} [{iss['state']}] {iss['title'][:70]}")
                    return ToolOutput(result="\n".join(lines))

                elif input.operation == "create_issue":
                    if not all([input.owner, input.repo, input.title]):
                        return ToolOutput(result="[github_ops: owner, repo, title required for create_issue]")
                    payload = {"title": input.title, "body": input.body, "labels": input.labels}
                    resp = await client.post(f"{_repo_url()}/issues", headers=headers, json=payload)
                    resp.raise_for_status()
                    iss = resp.json()
                    return ToolOutput(result=f"Created issue #{iss['number']}: {iss['html_url']}")

                elif input.operation == "trigger_workflow":
                    if not input.workflow_id:
                        return ToolOutput(result="[github_ops: workflow_id required for trigger_workflow]")
                    resp = await client.post(
                        f"{_repo_url()}/actions/workflows/{input.workflow_id}/dispatches",
                        headers=headers,
                        json={"ref": input.ref},
                    )
                    if resp.status_code == 204:
                        return ToolOutput(result=f"Triggered workflow '{input.workflow_id}' on ref '{input.ref}'")
                    resp.raise_for_status()
                    return ToolOutput(result=f"Trigger response: {resp.status_code}")

                else:
                    return ToolOutput(result=f"[github_ops: unknown operation '{input.operation}']")

        except Exception as exc:
            return ToolOutput(result=f"[github_ops: {exc}]")
