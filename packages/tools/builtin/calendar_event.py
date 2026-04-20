"""calendar_event — generate an .ics calendar event file."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class CalendarEventInput(BaseModel):
    title: str = Field(description="Event title / summary.")
    start_iso: str = Field(description="Start datetime in ISO 8601 format, e.g. '2025-11-01T10:00:00+00:00'.")
    end_iso: str = Field(description="End datetime in ISO 8601 format, e.g. '2025-11-01T11:00:00+00:00'.")
    filename: str = Field(description="Output .ics file path, e.g. ~/Desktop/meeting.ics")
    description: str = Field(default="", description="Event description / body text.")
    location: str = Field(default="", description="Event location or video call link.")
    attendees: list[str] = Field(default_factory=list, description="List of attendee email addresses.")
    organizer_email: str = Field(default="noreply@citnega.local", description="Organiser email address.")
    organizer_name: str = Field(default="citnega", description="Organiser display name.")
    all_day: bool = Field(default=False, description="If True, create an all-day event (ignores time component).")


def _fmt_dt(iso: str, all_day: bool) -> str:
    """Format ISO datetime string to iCalendar VALUE=DATE or DATE-TIME."""
    dt = datetime.fromisoformat(iso)
    if all_day:
        return dt.strftime("%Y%m%d")
    # Convert to UTC
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _esc(text: str) -> str:
    """Escape iCalendar text field special characters."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


class CalendarEventTool(BaseCallable):
    """Generate a standard .ics calendar event file importable into any calendar app."""

    name = "calendar_event"
    description = (
        "Create a calendar event as a standard .ics file. "
        "The file can be imported into Google Calendar, Outlook, Apple Calendar, or any iCal-compatible app. "
        "Supports: title, start/end time, description, location, and attendees."
    )
    callable_type = CallableType.TOOL
    input_schema = CalendarEventInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=10.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: CalendarEventInput, context: CallContext) -> ToolOutput:
        try:
            start_str = _fmt_dt(input.start_iso, input.all_day)
            end_str = _fmt_dt(input.end_iso, input.all_day)
        except Exception as exc:
            return ToolOutput(result=f"[calendar_event: invalid datetime format: {exc}. Use ISO 8601, e.g. 2025-11-01T10:00:00+00:00]")

        now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        event_uid = str(uuid.uuid4())
        dt_prop = "DATE" if input.all_day else "DATE-TIME"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//citnega//calendar_event//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:REQUEST",
            "BEGIN:VEVENT",
            f"UID:{event_uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE={dt_prop}:{start_str}",
            f"DTEND;VALUE={dt_prop}:{end_str}",
            f"SUMMARY:{_esc(input.title)}",
        ]

        if input.description:
            lines.append(f"DESCRIPTION:{_esc(input.description)}")
        if input.location:
            lines.append(f"LOCATION:{_esc(input.location)}")

        lines.append(f"ORGANIZER;CN={_esc(input.organizer_name)}:MAILTO:{input.organizer_email}")

        for attendee in input.attendees:
            lines.append(f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:MAILTO:{attendee}")

        lines += [
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR",
        ]

        ics_text = "\r\n".join(lines) + "\r\n"

        out_path = Path(input.filename).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_path.write_text(ics_text, encoding="utf-8")
        except Exception as exc:
            return ToolOutput(result=f"[calendar_event: failed to write file: {exc}]")

        attendee_note = f"  Attendees: {', '.join(input.attendees)}" if input.attendees else ""
        return ToolOutput(
            result=(
                f"Calendar event created: {out_path}\n"
                f"  Title: {input.title}\n"
                f"  Start: {input.start_iso}\n"
                f"  End:   {input.end_iso}"
                + (f"\n  Location: {input.location}" if input.location else "")
                + attendee_note
                + "\n\nImport the .ics file into Google Calendar, Outlook, or Apple Calendar."
            )
        )
