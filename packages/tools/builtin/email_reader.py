"""email_reader — read and search emails via IMAP."""

from __future__ import annotations

import email
import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class EmailReaderInput(BaseModel):
    action: str = Field(description="Action: 'search' | 'fetch_thread' | 'fetch_message'")
    query: str = Field(default="", description="Search query or IMAP search criteria (e.g. 'FROM user@example.com SUBJECT hello').")
    message_id: str = Field(default="", description="Message UID for fetch_message.")
    max_results: int = Field(default=10)
    folder: str = Field(default="INBOX", description="Mailbox folder name.")


class EmailReaderTool(BaseCallable):
    name = "email_reader"
    description = (
        "Search and read emails via IMAP. Supports full-text search and thread fetch. "
        "Requires EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD environment variables."
    )
    callable_type = CallableType.TOOL
    input_schema = EmailReaderInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: EmailReaderInput, context: CallContext) -> ToolOutput:
        host = os.environ.get("EMAIL_HOST", "")
        user = os.environ.get("EMAIL_USER", "")
        password = os.environ.get("EMAIL_PASSWORD", "")
        if not all([host, user, password]):
            return ToolOutput(result="[email_reader: EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD env vars required]")

        try:
            import imaplib
        except ImportError:
            return ToolOutput(result="[email_reader: imaplib not available]")

        try:
            import asyncio
            return await asyncio.to_thread(self._sync_execute, input, host, user, password)
        except Exception as exc:
            return ToolOutput(result=f"[email_reader: {exc}]")

    def _sync_execute(self, input: EmailReaderInput, host: str, user: str, password: str) -> ToolOutput:
        import imaplib

        try:
            conn = imaplib.IMAP4_SSL(host)
            conn.login(user, password)
        except Exception as exc:
            return ToolOutput(result=f"[email_reader: connection failed — {exc}]")

        try:
            conn.select(input.folder)

            if input.action == "search":
                criteria = input.query or "ALL"
                _, data = conn.uid("search", None, criteria)
                uids = (data[0] or b"").split()[-input.max_results:]
                if not uids:
                    return ToolOutput(result="[email_reader: no messages found]")
                lines = [f"Found {len(uids)} message(s):"]
                for uid in uids:
                    _, msg_data = conn.uid("fetch", uid, "(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])")
                    if msg_data and msg_data[0]:
                        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
                        msg = email.message_from_bytes(raw)
                        lines.append(
                            f"  UID {uid.decode()} | From: {msg.get('From', '?')[:50]} | "
                            f"Subject: {msg.get('Subject', '?')[:60]} | Date: {msg.get('Date', '?')}"
                        )
                return ToolOutput(result="\n".join(lines))

            elif input.action in ("fetch_message", "fetch_thread"):
                uid = input.message_id.encode() if input.message_id else b""
                if not uid:
                    return ToolOutput(result="[email_reader: message_id required for fetch_message]")
                _, msg_data = conn.uid("fetch", uid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    return ToolOutput(result=f"[email_reader: message UID {input.message_id} not found]")
                raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
                msg = email.message_from_bytes(raw)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="replace")
                return ToolOutput(result=(
                    f"From: {msg.get('From', '?')}\n"
                    f"Subject: {msg.get('Subject', '?')}\n"
                    f"Date: {msg.get('Date', '?')}\n"
                    f"Body:\n{body[:3000]}"
                ))

            else:
                return ToolOutput(result=f"[email_reader: unknown action '{input.action}']")

        finally:
            try:
                conn.logout()
            except Exception:
                pass
