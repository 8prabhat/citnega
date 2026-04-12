"""
Full Citnega error hierarchy.

Every error has a stable ``error_code`` string for programmatic handling and
observability. All errors capture an optional ``original`` exception for
wrapping lower-level failures without losing the root cause.

Error flow:
  - Lower layers raise typed subclasses.
  - ``BaseCallable.invoke()`` catches CitnegaError → wraps in InvokeResult.error.
  - Unhandled exceptions become UnhandledCallableError.
  - Service layer converts errors to ErrorEvent for streaming.
  - TUI renders ErrorBlock; CLI maps error_code to exit code.
"""

from __future__ import annotations


class CitnegaError(Exception):
    """Root of all Citnega application errors."""

    error_code: str = "CITNEGA_ERROR"

    def __init__(self, message: str, *, original: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.original = original

    def to_dict(self) -> dict[str, object]:
        """Serialise for event emission and logging."""
        data: dict[str, object] = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.original is not None:
            data["original_type"] = type(self.original).__name__
            data["original_message"] = str(self.original)
        return data

    def __repr__(self) -> str:
        return f"{type(self).__name__}(error_code={self.error_code!r}, message={self.message!r})"


# ── Configuration and startup ──────────────────────────────────────────────────


class ConfigError(CitnegaError):
    error_code = "CONFIG_ERROR"


class MissingConfigError(ConfigError):
    """Required configuration key or file is absent."""

    error_code = "CONFIG_MISSING"


class InvalidConfigError(ConfigError):
    """Configuration value is present but invalid."""

    error_code = "CONFIG_INVALID"


# ── Framework adapter ──────────────────────────────────────────────────────────


class AdapterError(CitnegaError):
    error_code = "ADAPTER_ERROR"


class UnknownFrameworkError(AdapterError):
    """No adapter registered for the requested framework name."""

    error_code = "ADAPTER_UNKNOWN"


class AdapterInitError(AdapterError):
    """Framework adapter failed to initialise."""

    error_code = "ADAPTER_INIT_FAILED"


class FrameworkRunnerError(AdapterError):
    """Error during session-scoped runner execution."""

    error_code = "ADAPTER_RUNNER_ERROR"


# ── Callable execution ─────────────────────────────────────────────────────────


class CallableError(CitnegaError):
    error_code = "CALLABLE_ERROR"


class UnhandledCallableError(CallableError):
    """An unexpected exception escaped a callable's _execute()."""

    error_code = "CALLABLE_UNHANDLED"


class CallableNotFoundError(CallableError):
    """No callable registered under the requested name."""

    error_code = "CALLABLE_NOT_FOUND"


class CallableValidationError(CallableError):
    """Input to a callable failed Pydantic validation."""

    error_code = "CALLABLE_VALIDATION"


# ── Policy enforcement ─────────────────────────────────────────────────────────


class CallablePolicyError(CallableError):
    """Base for all policy violations (subclass of CallableError)."""

    error_code = "POLICY_ERROR"


class CallableTimeoutError(CallablePolicyError):
    """Callable exceeded its allowed execution time."""

    error_code = "POLICY_TIMEOUT"


class CallableDepthError(CallablePolicyError):
    """Callable attempted to recurse beyond the configured depth limit."""

    error_code = "POLICY_DEPTH"


class PathNotAllowedError(CallablePolicyError):
    """Callable attempted to access a path outside its allowlist."""

    error_code = "POLICY_PATH"


class NetworkNotAllowedError(CallablePolicyError):
    """Callable attempted network access when not permitted."""

    error_code = "POLICY_NETWORK"


class OutputTooLargeError(CallablePolicyError):
    """Callable output exceeded the configured byte limit."""

    error_code = "POLICY_OUTPUT_SIZE"


class ApprovalDeniedError(CallablePolicyError):
    """User explicitly denied the approval request."""

    error_code = "POLICY_APPROVAL_DENIED"


class ApprovalTimeoutError(CallablePolicyError):
    """Approval request timed out without a user response."""

    error_code = "POLICY_APPROVAL_TIMEOUT"


# ── Model gateway ──────────────────────────────────────────────────────────────


class ModelGatewayError(CitnegaError):
    error_code = "GATEWAY_ERROR"


class NoHealthyProviderError(ModelGatewayError):
    """No model provider is healthy and able to serve the request."""

    error_code = "GATEWAY_NO_PROVIDER"


class RateLimitExceededError(ModelGatewayError):
    """Rate limit wait would exceed the request timeout."""

    error_code = "GATEWAY_RATE_LIMIT"


class ProviderHTTPError(ModelGatewayError):
    """HTTP-level error from a model provider endpoint."""

    error_code = "GATEWAY_HTTP"


class ModelCapabilityError(ModelGatewayError):
    """No provider supports the required capability."""

    error_code = "GATEWAY_CAPABILITY"


# ── Storage ────────────────────────────────────────────────────────────────────


class StorageError(CitnegaError):
    error_code = "STORAGE_ERROR"


class MigrationError(StorageError):
    """Alembic migration failed."""

    error_code = "STORAGE_MIGRATION"


class RepositoryError(StorageError):
    """Database repository operation failed."""

    error_code = "STORAGE_REPO"


class ArtifactError(StorageError):
    """Filesystem artifact store operation failed."""

    error_code = "STORAGE_ARTIFACT"


# ── Knowledge base ─────────────────────────────────────────────────────────────


class KnowledgeBaseError(CitnegaError):
    error_code = "KB_ERROR"


class KBItemNotFoundError(KnowledgeBaseError):
    """Requested KB item does not exist."""

    error_code = "KB_NOT_FOUND"


class KBIndexError(KnowledgeBaseError):
    """FTS5 index operation failed."""

    error_code = "KB_INDEX"


# ── Runtime and session ────────────────────────────────────────────────────────


class RuntimeError(CitnegaError):
    error_code = "RUNTIME_ERROR"


class SessionNotFoundError(RuntimeError):
    error_code = "SESSION_NOT_FOUND"


class RunNotFoundError(RuntimeError):
    error_code = "RUN_NOT_FOUND"


class InvalidRunStateError(RuntimeError):
    """A run state transition was attempted that is not allowed."""

    error_code = "RUN_STATE_INVALID"


# ── Service layer ──────────────────────────────────────────────────────────────


class ServiceError(CitnegaError):
    error_code = "SERVICE_ERROR"


# ── Security ───────────────────────────────────────────────────────────────────


class SecurityError(CitnegaError):
    error_code = "SECURITY_ERROR"


class KeyStoreError(SecurityError):
    """Key store read/write operation failed."""

    error_code = "SECURITY_KEYSTORE"


# ── CLI exit code mapping ──────────────────────────────────────────────────────

#: Maps error_code prefixes to CLI exit codes.
EXIT_CODE_MAP: dict[str, int] = {
    "CONFIG_": 2,
    "ADAPTER_": 3,
    "GATEWAY_": 4,
    "STORAGE_": 5,
}


def error_to_exit_code(error: CitnegaError) -> int:
    """Return the appropriate CLI exit code for a CitnegaError."""
    for prefix, code in EXIT_CODE_MAP.items():
        if error.error_code.startswith(prefix):
            return code
    return 1
