"""Adapter base package — shared classes for all framework adapters."""

from citnega.packages.adapters.base.base_adapter import BaseFrameworkAdapter
from citnega.packages.adapters.base.base_callable_factory import BaseCallableFactory
from citnega.packages.adapters.base.base_runner import BaseFrameworkRunner
from citnega.packages.adapters.base.cancellation import CancellationToken
from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
from citnega.packages.adapters.base.event_translator import EventTranslator

__all__ = [
    "BaseCallableFactory",
    "BaseFrameworkAdapter",
    "BaseFrameworkRunner",
    "CancellationToken",
    "CheckpointSerializer",
    "EventTranslator",
]
