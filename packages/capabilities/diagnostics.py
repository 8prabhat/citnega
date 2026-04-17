from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CapabilityLoadFailure:
    capability_id: str
    source: str
    path: str
    error: str
    required: bool = False


@dataclass(slots=True)
class CapabilityDiagnostics:
    failures: list[CapabilityLoadFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_failure(
        self,
        capability_id: str,
        *,
        source: str,
        path: str,
        error: str,
        required: bool = False,
    ) -> None:
        self.failures.append(
            CapabilityLoadFailure(
                capability_id=capability_id,
                source=source,
                path=path,
                error=error,
                required=required,
            )
        )

    def extend(self, other: CapabilityDiagnostics) -> None:
        self.failures.extend(other.failures)
        self.warnings.extend(other.warnings)

    @property
    def has_required_failures(self) -> bool:
        return any(item.required for item in self.failures)
