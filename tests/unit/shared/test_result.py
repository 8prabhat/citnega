"""Unit tests for packages/shared/result.py."""

from __future__ import annotations

import pytest

from citnega.packages.shared.result import Err, Ok, Result


class TestOk:
    def test_is_ok(self) -> None:
        assert Ok(42).is_ok() is True

    def test_is_err(self) -> None:
        assert Ok(42).is_err() is False

    def test_unwrap(self) -> None:
        assert Ok("hello").unwrap() == "hello"

    def test_unwrap_err_raises(self) -> None:
        with pytest.raises(ValueError, match="unwrap_err"):
            Ok(42).unwrap_err()

    def test_unwrap_or(self) -> None:
        assert Ok(5).unwrap_or(99) == 5

    def test_repr(self) -> None:
        assert repr(Ok(1)) == "Ok(1)"

    def test_equality(self) -> None:
        assert Ok(1) == Ok(1)
        assert Ok(1) != Ok(2)


class TestErr:
    def test_is_ok(self) -> None:
        assert Err(ValueError("e")).is_ok() is False

    def test_is_err(self) -> None:
        assert Err(ValueError("e")).is_err() is True

    def test_unwrap_raises(self) -> None:
        err = Err(ValueError("root"))
        with pytest.raises(ValueError):
            err.unwrap()

    def test_unwrap_err(self) -> None:
        exc = ValueError("root cause")
        result = Err(exc)
        assert result.unwrap_err() is exc

    def test_unwrap_or(self) -> None:
        assert Err(ValueError("e")).unwrap_or(99) == 99

    def test_repr(self) -> None:
        assert "Err" in repr(Err(ValueError("e")))

    def test_equality_same_type(self) -> None:
        assert Err(ValueError("a")) == Err(ValueError("b"))   # same type

    def test_equality_different_type(self) -> None:
        assert Err(ValueError("a")) != Err(TypeError("a"))


class TestResultPolymorphism:
    def test_result_is_base(self) -> None:
        ok: Result[int, ValueError] = Ok(1)
        err: Result[int, ValueError] = Err(ValueError("e"))
        assert ok.is_ok()
        assert err.is_err()
