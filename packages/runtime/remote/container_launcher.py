"""Container launcher for the reference remote worker service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ContainerMount:
    host_path: Path
    container_path: str


@dataclass(frozen=True)
class RemoteWorkerContainerLaunch:
    runtime: str
    image: str
    command: tuple[str, ...]
    container_name: str
    display_endpoint: str
    mounts: tuple[ContainerMount, ...]


_CONTAINER_WORKSPACE_PATH = "/workspace"
_CONTAINER_APP_HOME_PATH = "/citnega-app"
_CONTAINER_DB_ROOT_PATH = "/citnega-db"
_CONTAINER_TLS_CERT_ROOT_PATH = "/citnega-tls-cert"
_CONTAINER_TLS_KEY_ROOT_PATH = "/citnega-tls-key"
_CONTAINER_TLS_CLIENT_CA_ROOT_PATH = "/citnega-tls-client-ca"
_SUPPORTED_CONTAINER_RUNTIMES = {"docker", "podman"}


def build_remote_worker_container_launch(
    *,
    runtime: str,
    image: str,
    worker_id: str,
    host: str,
    port: int,
    allow_callables: list[str] | tuple[str, ...],
    app_home: Path,
    workspace_root: Path,
    db_path: Path | None = None,
    run_migrations: bool = True,
    container_name: str = "",
    signing_key: str = "",
    signing_key_id: str = "current",
    verification_keys: list[str] | tuple[str, ...] | None = None,
    auth_token: str = "",
    tls_cert_path: Path | None = None,
    tls_key_path: Path | None = None,
    tls_client_ca_path: Path | None = None,
    tls_require_client_cert: bool = False,
) -> RemoteWorkerContainerLaunch:
    """Build a concrete container launch plan for `citnega remote serve`."""
    effective_runtime = runtime.strip().lower()
    if effective_runtime not in _SUPPORTED_CONTAINER_RUNTIMES:
        raise ValueError(
            f"Unsupported container runtime {runtime!r}. Supported: {sorted(_SUPPORTED_CONTAINER_RUNTIMES)}."
        )
    effective_image = image.strip()
    if not effective_image:
        raise ValueError("Container image is required for container isolation profile.")
    if int(port) < 1:
        raise ValueError("Containerized remote worker requires a fixed port >= 1.")
    if not allow_callables:
        raise ValueError("Containerized remote worker requires a non-empty callable allowlist.")

    resolved_workspace = workspace_root.expanduser().resolve()
    resolved_app_home = app_home.expanduser().resolve()
    resolved_db_path = db_path.expanduser().resolve() if db_path is not None else None
    resolved_tls_cert_path = tls_cert_path.expanduser().resolve() if tls_cert_path is not None else None
    resolved_tls_key_path = tls_key_path.expanduser().resolve() if tls_key_path is not None else None
    resolved_tls_client_ca_path = (
        tls_client_ca_path.expanduser().resolve() if tls_client_ca_path is not None else None
    )

    mounts = [ContainerMount(host_path=resolved_workspace, container_path=_CONTAINER_WORKSPACE_PATH)]
    app_home_in_container = _map_or_add_mount(
        path=resolved_app_home,
        mounts=mounts,
        fallback_container_root=_CONTAINER_APP_HOME_PATH,
    )
    db_path_in_container = ""
    if resolved_db_path is not None:
        db_path_in_container = _map_or_add_mount(
            path=resolved_db_path,
            mounts=mounts,
            fallback_container_root=_CONTAINER_DB_ROOT_PATH,
            mount_parent=True,
        )
    tls_cert_path_in_container = ""
    tls_key_path_in_container = ""
    tls_client_ca_path_in_container = ""
    if resolved_tls_cert_path is not None:
        tls_cert_path_in_container = _map_or_add_mount(
            path=resolved_tls_cert_path,
            mounts=mounts,
            fallback_container_root=_CONTAINER_TLS_CERT_ROOT_PATH,
            mount_parent=True,
        )
    if resolved_tls_key_path is not None:
        tls_key_path_in_container = _map_or_add_mount(
            path=resolved_tls_key_path,
            mounts=mounts,
            fallback_container_root=_CONTAINER_TLS_KEY_ROOT_PATH,
            mount_parent=True,
        )
    if resolved_tls_client_ca_path is not None:
        tls_client_ca_path_in_container = _map_or_add_mount(
            path=resolved_tls_client_ca_path,
            mounts=mounts,
            fallback_container_root=_CONTAINER_TLS_CLIENT_CA_ROOT_PATH,
            mount_parent=True,
        )

    effective_name = container_name.strip() or _default_container_name(worker_id=worker_id, port=port)
    command: list[str] = [
        effective_runtime,
        "run",
        "--rm",
        "--name",
        effective_name,
        "-p",
        f"{host}:{port}:{port}",
        "--workdir",
        _CONTAINER_WORKSPACE_PATH,
    ]
    for mount in mounts:
        command.extend(
            [
                "--mount",
                f"type=bind,src={mount.host_path},dst={mount.container_path}",
            ]
        )

    env_items = {
        "CITNEGA_REMOTE_IN_CONTAINER": "1",
        "CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY": signing_key,
        "CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID": signing_key_id,
    }
    if verification_keys:
        env_items["CITNEGA_REMOTE_ENVELOPE_VERIFICATION_KEYS"] = json.dumps(
            list(verification_keys),
            ensure_ascii=True,
        )
    if auth_token.strip():
        env_items["CITNEGA_REMOTE_AUTH_TOKEN"] = auth_token.strip()

    for key, value in env_items.items():
        command.extend(["-e", f"{key}={value}"])

    command.extend(
        [
            effective_image,
            "python",
            "-m",
            "citnega.apps.cli.main",
            "remote",
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--isolation-profile",
            "container",
            "--worker-id",
            worker_id,
            "--app-home",
            app_home_in_container,
            "--run-migrations" if run_migrations else "--no-run-migrations",
        ]
    )
    if db_path_in_container:
        command.extend(["--db-path", db_path_in_container])
    if tls_cert_path_in_container:
        command.extend(["--tls-cert-file", tls_cert_path_in_container])
    if tls_key_path_in_container:
        command.extend(["--tls-key-file", tls_key_path_in_container])
    if tls_client_ca_path_in_container:
        command.extend(["--tls-client-ca-file", tls_client_ca_path_in_container])
    if tls_require_client_cert:
        command.append("--tls-require-client-cert")
    for callable_name in allow_callables:
        command.extend(["--allow-callable", str(callable_name)])

    scheme = "https" if tls_cert_path_in_container and tls_key_path_in_container else "http"
    return RemoteWorkerContainerLaunch(
        runtime=effective_runtime,
        image=effective_image,
        command=tuple(command),
        container_name=effective_name,
        display_endpoint=f"{scheme}://{host}:{port}",
        mounts=tuple(mounts),
    )


async def run_remote_worker_container(launch: RemoteWorkerContainerLaunch) -> int:
    """Execute the containerized remote worker until it exits."""
    try:
        process = await asyncio.create_subprocess_exec(*launch.command)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Container runtime {launch.runtime!r} was not found on PATH."
        ) from exc

    try:
        return await process.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        raise


def _map_or_add_mount(
    *,
    path: Path,
    mounts: list[ContainerMount],
    fallback_container_root: str,
    mount_parent: bool = False,
) -> str:
    mapped = _map_path(path, mounts)
    if mapped:
        return mapped

    host_root = path.parent if mount_parent else path
    container_root = fallback_container_root
    mounts.append(ContainerMount(host_path=host_root, container_path=container_root))
    mapped = _map_path(path, mounts)
    if not mapped:
        raise ValueError(f"Could not map host path {path} into the container launch plan.")
    return mapped


def _map_path(path: Path, mounts: list[ContainerMount]) -> str:
    resolved = path.expanduser().resolve()
    for mount in mounts:
        if resolved == mount.host_path:
            return mount.container_path
        if mount.host_path in resolved.parents:
            rel = resolved.relative_to(mount.host_path)
            return f"{mount.container_path}/{rel.as_posix()}"
    return ""


def _default_container_name(*, worker_id: str, port: int) -> str:
    base = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in (worker_id.strip() or "remote-worker")
    ).strip("-_")
    if not base:
        base = "remote-worker"
    return f"citnega-{base}-{port}"
