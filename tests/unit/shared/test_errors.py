"""Unit tests for packages/shared/errors.py."""

from __future__ import annotations

from citnega.packages.shared.errors import (
    AdapterError,
    ApprovalDeniedError,
    CallablePolicyError,
    CitnegaError,
    ConfigError,
    InvalidConfigError,
    KeyStoreError,
    MissingConfigError,
    ModelGatewayError,
    NoHealthyProviderError,
    RunNotFoundError,
    RuntimeError,
    SecurityError,
    StorageError,
    error_to_exit_code,
)


class TestCitnegaError:
    def test_basic_construction(self) -> None:
        err = CitnegaError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.message == "something went wrong"
        assert err.original is None
        assert err.error_code == "CITNEGA_ERROR"

    def test_with_original(self) -> None:
        orig = ValueError("root cause")
        err = CitnegaError("wrapper", original=orig)
        assert err.original is orig

    def test_to_dict(self) -> None:
        err = CitnegaError("test")
        d = err.to_dict()
        assert d["error_code"] == "CITNEGA_ERROR"
        assert d["message"] == "test"
        assert "original_type" not in d

    def test_to_dict_with_original(self) -> None:
        orig = ValueError("root")
        err = CitnegaError("wrapper", original=orig)
        d = err.to_dict()
        assert d["original_type"] == "ValueError"
        assert d["original_message"] == "root"

    def test_repr(self) -> None:
        err = CitnegaError("msg")
        assert "CITNEGA_ERROR" in repr(err)
        assert "msg" in repr(err)


class TestErrorHierarchy:
    def test_config_error_is_citnega_error(self) -> None:
        err = ConfigError("bad config")
        assert isinstance(err, CitnegaError)
        assert err.error_code == "CONFIG_ERROR"

    def test_missing_config_is_config_error(self) -> None:
        err = MissingConfigError("missing key")
        assert isinstance(err, ConfigError)
        assert isinstance(err, CitnegaError)
        assert err.error_code == "CONFIG_MISSING"

    def test_invalid_config_error(self) -> None:
        assert InvalidConfigError("x").error_code == "CONFIG_INVALID"

    def test_adapter_hierarchy(self) -> None:
        assert AdapterError("x").error_code == "ADAPTER_ERROR"
        assert isinstance(AdapterError("x"), CitnegaError)

    def test_policy_error_is_callable_error(self) -> None:
        err = CallablePolicyError("depth exceeded")
        from citnega.packages.shared.errors import CallableError

        assert isinstance(err, CallableError)
        assert isinstance(err, CitnegaError)

    def test_approval_denied_is_policy_error(self) -> None:
        err = ApprovalDeniedError("denied")
        assert isinstance(err, CallablePolicyError)
        assert err.error_code == "POLICY_APPROVAL_DENIED"

    def test_no_healthy_provider_is_gateway_error(self) -> None:
        err = NoHealthyProviderError("no providers")
        assert isinstance(err, ModelGatewayError)

    def test_storage_hierarchy(self) -> None:
        err = StorageError("disk full")
        assert isinstance(err, CitnegaError)

    def test_runtime_hierarchy(self) -> None:
        err = RunNotFoundError("not found")
        assert isinstance(err, RuntimeError)

    def test_security_hierarchy(self) -> None:
        err = KeyStoreError("keyring failed")
        assert isinstance(err, SecurityError)
        assert isinstance(err, CitnegaError)


class TestExitCodes:
    def test_config_error_exit_code(self) -> None:
        assert error_to_exit_code(ConfigError("x")) == 2

    def test_adapter_error_exit_code(self) -> None:
        assert error_to_exit_code(AdapterError("x")) == 3

    def test_gateway_error_exit_code(self) -> None:
        assert error_to_exit_code(ModelGatewayError("x")) == 4

    def test_storage_error_exit_code(self) -> None:
        assert error_to_exit_code(StorageError("x")) == 5

    def test_unknown_error_exit_code(self) -> None:
        assert error_to_exit_code(CitnegaError("x")) == 1
