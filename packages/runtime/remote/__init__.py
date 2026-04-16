"""Remote execution primitives."""

from citnega.packages.runtime.remote.container_launcher import (
    ContainerMount,
    RemoteWorkerContainerLaunch,
    build_remote_worker_container_launch,
    run_remote_worker_container,
)
from citnega.packages.runtime.remote.envelopes import (
    EnvelopeSigner,
    EnvelopeVerificationResult,
    RemoteRunEnvelope,
    build_run_envelope,
    parse_verification_keys,
    payload_sha256,
)
from citnega.packages.runtime.remote.executor import (
    HttpRemoteWorkerPool,
    InProcessRemoteWorkerPool,
    RemoteDispatchReport,
)
from citnega.packages.runtime.remote.secret_bootstrap import (
    RemoteSecretBundle,
    build_remote_secret_bundle,
    default_rotation_key_id,
    render_secret_bundle_json,
    render_secret_bundle_text,
)
from citnega.packages.runtime.remote.service import (
    RemoteInvokeRequest,
    RemoteInvokeResponse,
    RemoteInvokeSession,
    RemoteWorkerHTTPService,
    RemoteWorkerTLSConfig,
    build_remote_callable_registry,
)

__all__ = [
    "ContainerMount",
    "EnvelopeSigner",
    "EnvelopeVerificationResult",
    "HttpRemoteWorkerPool",
    "InProcessRemoteWorkerPool",
    "RemoteDispatchReport",
    "RemoteInvokeRequest",
    "RemoteInvokeResponse",
    "RemoteInvokeSession",
    "RemoteRunEnvelope",
    "RemoteSecretBundle",
    "RemoteWorkerContainerLaunch",
    "RemoteWorkerHTTPService",
    "RemoteWorkerTLSConfig",
    "build_remote_callable_registry",
    "build_remote_secret_bundle",
    "build_remote_worker_container_launch",
    "build_run_envelope",
    "default_rotation_key_id",
    "parse_verification_keys",
    "payload_sha256",
    "render_secret_bundle_json",
    "render_secret_bundle_text",
    "run_remote_worker_container",
]
