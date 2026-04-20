"""EnvInspectorTool — safe environment inspection with sensitive value redaction."""

from __future__ import annotations

import os
import re

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType

_SENSITIVE_RE = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE|AUTH|API_KEY|ACCESS_KEY|"
    r"CLIENT_SECRET|SIGNING_KEY|ENCRYPTION_KEY|CERT|PEM|RSA|JWT)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


class EnvInspectorInput(BaseModel):
    filter_prefix: str = ""       # only show vars starting with this prefix
    include_packages: bool = False # list installed Python packages
    show_sensitive: bool = False   # NEVER show actual values of sensitive vars


class EnvEntry(BaseModel):
    name: str
    value: str
    is_redacted: bool


class EnvInspectorOutput(BaseModel):
    env_vars: list[EnvEntry]
    total: int
    redacted_count: int
    packages: list[str] | None = None


class EnvInspectorTool(BaseCallable):
    name = "env_inspector"
    description = (
        "List environment variables with automatic redaction of sensitive values "
        "(API keys, secrets, tokens, passwords). Optionally list installed Python packages."
    )
    callable_type = CallableType.TOOL
    input_schema = EnvInspectorInput
    output_schema = EnvInspectorOutput

    async def _execute(self, input_data: EnvInspectorInput, context: object) -> EnvInspectorOutput:
        entries: list[EnvEntry] = []
        redacted_count = 0

        for name, value in sorted(os.environ.items()):
            if input_data.filter_prefix and not name.startswith(input_data.filter_prefix):
                continue
            is_sensitive = bool(_SENSITIVE_RE.search(name))
            if is_sensitive and not input_data.show_sensitive:
                entries.append(EnvEntry(name=name, value=_REDACTED, is_redacted=True))
                redacted_count += 1
            else:
                entries.append(EnvEntry(name=name, value=value, is_redacted=False))

        packages: list[str] | None = None
        if input_data.include_packages:
            try:
                import importlib.metadata as meta
                packages = sorted(f"{d.name}=={d.version}" for d in meta.distributions())
            except Exception:
                packages = []

        return EnvInspectorOutput(
            env_vars=entries,
            total=len(entries),
            redacted_count=redacted_count,
            packages=packages,
        )
