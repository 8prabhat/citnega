"""Async-to-sync bridge for Typer commands."""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

_T = TypeVar("_T")


def run_async(coro_fn: Callable[..., Coroutine[Any, Any, _T]]) -> Callable[..., _T]:
    """
    Decorator: wraps an async function so that Typer (which is synchronous)
    can invoke it via ``asyncio.run()``.

    Usage::

        @app.command()
        @run_async
        async def my_command(...) -> None:
            ...
    """

    @functools.wraps(coro_fn)
    def wrapper(*args: Any, **kwargs: Any) -> _T:
        return asyncio.run(coro_fn(*args, **kwargs))

    return wrapper
