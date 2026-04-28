"""calendar_query — read Google Calendar events and find free slots."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class CalendarQueryInput(BaseModel):
    action: str = Field(description="Action: 'list_events' | 'find_free_slots' | 'get_event'")
    start_date: str = Field(default="", description="Start date/datetime in ISO 8601 (e.g. '2024-01-01' or '2024-01-01T09:00:00Z').")
    end_date: str = Field(default="", description="End date/datetime in ISO 8601.")
    calendar_id: str = Field(default="primary", description="Calendar ID (default: 'primary').")
    max_results: int = Field(default=20)
    event_id: str = Field(default="", description="Event ID for get_event.")
    duration_minutes: int = Field(default=60, description="Required slot duration in minutes for find_free_slots.")


class CalendarQueryTool(BaseCallable):
    name = "calendar_query"
    description = (
        "Read Google Calendar events, find free/busy slots. "
        "Requires GOOGLE_APPLICATION_CREDENTIALS or OAuth token. "
        "Install: pip install google-api-python-client google-auth"
    )
    callable_type = CallableType.TOOL
    input_schema = CalendarQueryInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: CalendarQueryInput, context: CallContext) -> ToolOutput:
        try:
            from googleapiclient.discovery import build  # noqa: F401
            from google.oauth2 import service_account  # noqa: F401
        except ImportError:
            return ToolOutput(result="[calendar_query: google-api-python-client not installed — run: pip install google-api-python-client google-auth]")

        try:
            import asyncio
            return await asyncio.to_thread(self._sync_execute, input)
        except Exception as exc:
            return ToolOutput(result=f"[calendar_query: {exc}]")

    def _sync_execute(self, input: CalendarQueryInput) -> ToolOutput:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        import google.auth

        creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        try:
            if creds_file:
                creds = service_account.Credentials.from_service_account_file(
                    creds_file,
                    scopes=["https://www.googleapis.com/auth/calendar.readonly"],
                )
            else:
                creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/calendar.readonly"]
                )
        except Exception as exc:
            return ToolOutput(result=f"[calendar_query: auth failed — {exc}. Set GOOGLE_APPLICATION_CREDENTIALS]")

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        if input.action == "list_events":
            params: dict = {
                "calendarId": input.calendar_id,
                "maxResults": input.max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if input.start_date:
                params["timeMin"] = _to_rfc3339(input.start_date)
            if input.end_date:
                params["timeMax"] = _to_rfc3339(input.end_date)
            result = service.events().list(**params).execute()
            events = result.get("items", [])
            if not events:
                return ToolOutput(result="[calendar_query: no events found in range]")
            lines = [f"Events ({len(events)}):"]
            for e in events:
                start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "?")
                lines.append(f"  {start} | {e.get('summary', '(no title)')[:80]}")
            return ToolOutput(result="\n".join(lines))

        elif input.action == "get_event":
            if not input.event_id:
                return ToolOutput(result="[calendar_query: event_id required for get_event]")
            e = service.events().get(calendarId=input.calendar_id, eventId=input.event_id).execute()
            start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "?")
            end = e.get("end", {}).get("dateTime") or e.get("end", {}).get("date", "?")
            return ToolOutput(result=(
                f"Title: {e.get('summary', '(no title)')}\n"
                f"Start: {start} | End: {end}\n"
                f"Location: {e.get('location', '')}\n"
                f"Description: {(e.get('description') or '')[:500]}"
            ))

        elif input.action == "find_free_slots":
            if not input.start_date or not input.end_date:
                return ToolOutput(result="[calendar_query: start_date and end_date required for find_free_slots]")
            body = {
                "timeMin": _to_rfc3339(input.start_date),
                "timeMax": _to_rfc3339(input.end_date),
                "items": [{"id": input.calendar_id}],
            }
            fb = service.freebusy().query(body=body).execute()
            busy = fb.get("calendars", {}).get(input.calendar_id, {}).get("busy", [])
            if not busy:
                return ToolOutput(result="No busy slots found — calendar appears free in the given range.")
            lines = [f"Busy slots ({len(busy)}):"]
            for slot in busy:
                lines.append(f"  {slot['start']} → {slot['end']}")
            return ToolOutput(result="\n".join(lines))

        else:
            return ToolOutput(result=f"[calendar_query: unknown action '{input.action}']")


def _to_rfc3339(dt_str: str) -> str:
    if "T" in dt_str:
        return dt_str if dt_str.endswith("Z") or "+" in dt_str else dt_str + "Z"
    return dt_str + "T00:00:00Z"
