"""slack_notifier — post a message to a Slack channel via Incoming Webhook."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SlackNotifierInput(BaseModel):
    webhook_url: str = Field(description="Slack Incoming Webhook URL (from Slack App configuration).")
    message: str = Field(description="Message text to post. Supports Slack mrkdwn formatting.")
    channel: str = Field(default="", description="Override channel (e.g. #alerts). Leave empty to use webhook default.")
    username: str = Field(default="citnega", description="Bot display name.")
    icon_emoji: str = Field(default=":robot_face:", description="Bot icon emoji, e.g. :bell:")
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional Slack attachments for structured messages.",
    )


class SlackNotifierTool(BaseCallable):
    """Post a message to a Slack channel via an Incoming Webhook URL."""

    name = "slack_notifier"
    description = (
        "Send a message to a Slack channel using a Slack Incoming Webhook URL. "
        "Supports plain text, mrkdwn formatting, and structured attachments. "
        "Requires a webhook URL from the user's Slack workspace app configuration."
    )
    callable_type = CallableType.TOOL
    input_schema = SlackNotifierInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=15.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: SlackNotifierInput, context: CallContext) -> ToolOutput:
        import httpx

        if not input.webhook_url.startswith("https://hooks.slack.com/"):
            return ToolOutput(result="[slack_notifier: webhook_url must be a valid Slack Incoming Webhook URL starting with https://hooks.slack.com/]")

        payload: dict[str, Any] = {
            "text": input.message,
            "username": input.username,
            "icon_emoji": input.icon_emoji,
        }
        if input.channel:
            payload["channel"] = input.channel
        if input.attachments:
            payload["attachments"] = input.attachments

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(input.webhook_url, json=payload)
                if resp.status_code == 200:
                    return ToolOutput(result=f"Message posted to Slack. Status: {resp.status_code} OK")
                return ToolOutput(result=f"[slack_notifier: Slack returned HTTP {resp.status_code}: {resp.text}]")
        except Exception as exc:
            return ToolOutput(result=f"[slack_notifier: request failed: {exc}]")
