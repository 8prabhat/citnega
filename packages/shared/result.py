"""
Result[T, E] — a typed two-variant return type for non-exception error flows.

Used by repositories and model providers to return either a successful value
or a typed error without raising, enabling explicit error handling at call sites.

Usage::

    def do_thing() -> Result[MyModel, StorageError]:
        try:
            val = expensive_operation()
            return Ok(val)
        except SomeException as e:
            return Err(StorageError("failed", original=e))

    result = do_thing()
    if result.is_ok():
        use(result.unwrap())
    else:
        handle(result.unwrap_err())
"""

from __future__ import annotations

from typing import Generic, NoReturn, TypeVar

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


class Result(Generic[T, E]):
    """Abstract base. Use Ok[T, E] or Err[T, E] directly."""

    def is_ok(self) -> bool:
        raise NotImplementedError

    def is_err(self) -> bool:
        return not self.is_ok()

    def unwrap(self) -> T:
        raise NotImplementedError

    def unwrap_err(self) -> E:
        raise NotImplementedError

    def unwrap_or(self, default: T) -> T:
        raise NotImplementedError


class Ok(Result[T, E]):
    """Successful result carrying a value."""

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    def is_ok(self) -> bool:
        return True

    def unwrap(self) -> T:
        return self._value

    def unwrap_err(self) -> NoReturn:
        raise ValueError(f"Called unwrap_err() on Ok({self._value!r})")

    def unwrap_or(self, default: T) -> T:
        return self._value

    def __repr__(self) -> str:
        return f"Ok({self._value!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Ok) and self._value == other._value


class Err(Result[T, E]):
    """Failed result carrying an error."""

    __slots__ = ("_error",)

    def __init__(self, error: E) -> None:
        self._error = error

    def is_ok(self) -> bool:
        return False

    def unwrap(self) -> NoReturn:
        raise ValueError(f"Called unwrap() on Err({self._error!r})") from self._error

    def unwrap_err(self) -> E:
        return self._error

    def unwrap_or(self, default: T) -> T:
        return default

    def __repr__(self) -> str:
        return f"Err({self._error!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Err) and type(self._error) is type(other._error)
