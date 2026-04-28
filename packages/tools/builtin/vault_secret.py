"""vault_secret — read secrets from HashiCorp Vault or environment variables."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


def _mask(value: str) -> str:
    if not value:
        return ""
    return value[:4] + "****"


class VaultSecretInput(BaseModel):
    secret_path: str = Field(description="Secret path (e.g. 'secret/data/myapp/db') or env var name.")
    field: str = Field(default="", description="Specific field within the secret. Empty = return all fields.")
    backend: str = Field(
        default="auto",
        description="Backend: 'vault' (HashiCorp Vault) | 'env' (os.environ) | 'auto' (try vault, fall back to env).",
    )


class VaultSecretTool(BaseCallable):
    name = "vault_secret"
    description = (
        "Read secrets from HashiCorp Vault (KV v2) or environment variables. "
        "Output is masked (first 4 chars + ****). "
        "Requires VAULT_ADDR and VAULT_TOKEN for vault backend."
    )
    callable_type = CallableType.TOOL
    input_schema = VaultSecretInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=20.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: VaultSecretInput, context: CallContext) -> ToolOutput:
        backend = input.backend.lower()

        if backend in ("env", "auto") and not os.environ.get("VAULT_ADDR"):
            return self._read_env(input)

        if backend == "vault" or (backend == "auto" and os.environ.get("VAULT_ADDR")):
            return await self._read_vault(input)

        return self._read_env(input)

    def _read_env(self, input: VaultSecretInput) -> ToolOutput:
        key = input.field or input.secret_path
        value = os.environ.get(key, "")
        if not value:
            return ToolOutput(result=f"[vault_secret: env var '{key}' not set]")
        return ToolOutput(result=f"{key} = {_mask(value)}")

    async def _read_vault(self, input: VaultSecretInput) -> ToolOutput:
        vault_addr = os.environ.get("VAULT_ADDR", "").rstrip("/")
        vault_token = os.environ.get("VAULT_TOKEN", "")
        if not vault_addr or not vault_token:
            return ToolOutput(result="[vault_secret: VAULT_ADDR and VAULT_TOKEN env vars required]")

        try:
            import httpx
        except ImportError:
            return ToolOutput(result="[vault_secret: httpx not installed — run: pip install httpx]")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{vault_addr}/v1/{input.secret_path}",
                    headers={"X-Vault-Token": vault_token},
                )
                if resp.status_code == 404:
                    return ToolOutput(result=f"[vault_secret: path '{input.secret_path}' not found in Vault]")
                resp.raise_for_status()
                data = resp.json().get("data", {})
                # KV v2 wraps data under data.data
                if "data" in data:
                    data = data["data"]
                if input.field:
                    val = data.get(input.field, "")
                    if not val:
                        return ToolOutput(result=f"[vault_secret: field '{input.field}' not found at path]")
                    return ToolOutput(result=f"{input.field} = {_mask(str(val))}")
                lines = [f"{k} = {_mask(str(v))}" for k, v in data.items()]
                return ToolOutput(result="\n".join(lines) or "[vault_secret: secret is empty]")
        except Exception as exc:
            return ToolOutput(result=f"[vault_secret: {exc}]")
