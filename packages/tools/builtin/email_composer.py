"""email_composer — compose a formatted email draft (does not send)."""

from __future__ import annotations

import email.utils
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class EmailComposerInput(BaseModel):
    to: list[str] = Field(description="Recipient email addresses.")
    subject: str = Field(description="Email subject line.")
    body: str = Field(description="Email body text (plain text or HTML).")
    cc: list[str] = Field(default_factory=list, description="CC recipients.")
    bcc: list[str] = Field(default_factory=list, description="BCC recipients.")
    from_name: str = Field(default="citnega", description="Sender display name.")
    from_email: str = Field(default="noreply@citnega.local", description="Sender email address.")
    html: bool = Field(default=False, description="If True, treat body as HTML.")
    output_file: str = Field(default="", description="Optional path to write the .eml file.")


class EmailComposerTool(BaseCallable):
    """
    Compose a formatted email draft.

    Does NOT send — outputs the formatted email as text and optionally writes
    a .eml file that can be opened or imported into any mail client.
    """

    name = "email_composer"
    description = (
        "Compose a formatted email draft (to, cc, bcc, subject, body). "
        "Does NOT send — returns the formatted email text and optionally writes a .eml file. "
        "Use this to draft emails for the user to review and send themselves."
    )
    callable_type = CallableType.TOOL
    input_schema = EmailComposerInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=10.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: EmailComposerInput, context: CallContext) -> ToolOutput:
        now = email.utils.formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)

        to_str = ", ".join(input.to)
        cc_str = ", ".join(input.cc) if input.cc else ""
        bcc_str = ", ".join(input.bcc) if input.bcc else ""
        from_str = email.utils.formataddr((input.from_name, input.from_email))
        content_type = "text/html" if input.html else "text/plain"

        lines = [
            f"From: {from_str}",
            f"To: {to_str}",
        ]
        if cc_str:
            lines.append(f"Cc: {cc_str}")
        if bcc_str:
            lines.append(f"Bcc: {bcc_str}")
        lines += [
            f"Subject: {input.subject}",
            f"Date: {now}",
            f"Content-Type: {content_type}; charset=utf-8",
            "MIME-Version: 1.0",
            "",
            input.body,
        ]
        eml_text = "\n".join(lines)

        file_note = ""
        if input.output_file:
            out_path = Path(input.output_file).expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                out_path.write_text(eml_text, encoding="utf-8")
                file_note = f"\n\n.eml saved: {out_path}"
            except Exception as exc:
                file_note = f"\n\n⚠ Could not write .eml file: {exc}"

        return ToolOutput(result=f"--- Email Draft ---\n{eml_text}{file_note}")
