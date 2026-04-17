from __future__ import annotations

from collections.abc import Iterable

from citnega.packages.capabilities.models import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityRecord,
)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._records: dict[str, CapabilityRecord] = {}

    def register(self, record: CapabilityRecord, *, overwrite: bool = False) -> None:
        capability_id = record.descriptor.capability_id
        if capability_id in self._records and not overwrite:
            raise ValueError(f"Capability {capability_id!r} is already registered.")
        self._records[capability_id] = record

    def register_many(self, records: Iterable[CapabilityRecord], *, overwrite: bool = False) -> None:
        for record in records:
            self.register(record, overwrite=overwrite)

    def get_descriptor(self, capability_id: str) -> CapabilityDescriptor | None:
        record = self._records.get(capability_id)
        return record.descriptor if record is not None else None

    def resolve_descriptor(self, capability_id: str) -> CapabilityDescriptor:
        descriptor = self.get_descriptor(capability_id)
        if descriptor is None:
            raise KeyError(f"Unknown capability {capability_id!r}.")
        return descriptor

    def get_runtime(self, capability_id: str) -> object | None:
        record = self._records.get(capability_id)
        return record.runtime_object if record is not None else None

    def list_all(self) -> list[CapabilityDescriptor]:
        return [record.descriptor for record in self._records.values()]

    def list_by_kind(self, kind: CapabilityKind) -> list[CapabilityDescriptor]:
        return [
            record.descriptor
            for record in self._records.values()
            if record.descriptor.kind == kind
        ]

    def list_runtime_capabilities(self) -> dict[str, object]:
        return {
            capability_id: record.runtime_object
            for capability_id, record in self._records.items()
            if record.runtime_object is not None
        }

    def __contains__(self, capability_id: object) -> bool:
        return capability_id in self._records

    def __len__(self) -> int:
        return len(self._records)
