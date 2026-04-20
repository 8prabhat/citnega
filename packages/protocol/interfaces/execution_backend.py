"""
IExecutionBackend — abstraction over shell command execution environments.

Concrete implementations: LocalExecutionBackend (default), DockerExecutionBackend.
RunShellTool receives this via DI so switching to Docker requires only config change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    """Result of a command executed by an IExecutionBackend."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = field(default=False)

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class IExecutionBackend(ABC):
    """Contract for executing shell commands in a controlled environment."""

    @abstractmethod
    async def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult: ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g. 'local', 'docker')."""
        ...
