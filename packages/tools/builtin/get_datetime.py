"""get_datetime — return the current date, time, and timezone.

This tool has no external dependencies. It exists because the model's training
cutoff means it does not know the current date — without this tool it cannot
reason correctly about "latest", "current", "today", etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class GetDatetimeInput(BaseModel):
    timezone: str = Field(
        default="local",
        description="'local' for system timezone, 'utc' for UTC, or an IANA name like 'Asia/Kolkata'.",
    )


class GetDatetimeTool(BaseCallable):
    """Returns the current date, time, day of week, and UTC offset."""

    name = "get_datetime"
    description = (
        "Get the current date and time. Call this first whenever the user asks about "
        "anything time-sensitive — you need to know today's date before deciding "
        "whether information might be stale and whether to search the web."
    )
    callable_type = CallableType.TOOL
    input_schema = GetDatetimeInput
    output_schema = ToolOutput
    policy = tool_policy(timeout_seconds=5.0, requires_approval=False, network_allowed=False)

    async def _execute(self, input: GetDatetimeInput, context: CallContext) -> ToolOutput:
        import datetime

        tz: datetime.timezone | None = None

        if input.timezone.lower() == "utc":
            tz = datetime.UTC
        elif input.timezone.lower() != "local":
            try:
                import zoneinfo
                tz_info = zoneinfo.ZoneInfo(input.timezone)
                now = datetime.datetime.now(tz_info)
            except Exception:
                now = datetime.datetime.now(datetime.UTC)
        else:
            now = datetime.datetime.now()

        if tz is not None:
            now = datetime.datetime.now(tz)

        fmt = now.strftime("%A, %d %B %Y  %H:%M:%S")
        utc_offset = now.strftime("%z") if now.tzinfo else "local time"
        day_of_year = now.timetuple().tm_yday
        week_num = now.isocalendar()[1]

        result = (
            f"{fmt}  (UTC{utc_offset})\n"
            f"Day of year: {day_of_year}   ISO week: {week_num}\n"
            f"Unix timestamp: {int(now.timestamp()) if now.tzinfo else int(now.replace(tzinfo=datetime.UTC).timestamp())}"
        )
        return ToolOutput(result=result)
