"""Unit tests for the remote worker container launcher."""

from __future__ import annotations

from pathlib import Path

from citnega.packages.runtime.remote.container_launcher import (
    build_remote_worker_container_launch,
)


def test_container_launch_builds_mounts_env_and_inner_command(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "citnega.db"
    db_path.write_text("", encoding="utf-8")

    launch = build_remote_worker_container_launch(
        runtime="docker",
        image="ghcr.io/acme/citnega:latest",
        worker_id="remote-service-1",
        host="127.0.0.1",
        port=8787,
        allow_callables=["qa_agent", "release_agent"],
        app_home=app_home,
        workspace_root=workspace,
        db_path=db_path,
        signing_key="secret",
        signing_key_id="2026-04",
        verification_keys=["2026-03=old-secret"],
        auth_token="token123",
    )

    command = list(launch.command)
    assert launch.runtime == "docker"
    assert launch.container_name == "citnega-remote-service-1-8787"
    assert launch.display_endpoint == "http://127.0.0.1:8787"
    assert any(arg == "CITNEGA_REMOTE_IN_CONTAINER=1" for arg in command)
    assert any(arg == "CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY=secret" for arg in command)
    assert any(arg == "CITNEGA_REMOTE_AUTH_TOKEN=token123" for arg in command)
    assert "--app-home" in command
    assert "/citnega-app" in command
    assert "--db-path" in command
    assert "/citnega-db/citnega.db" in command
    assert command[-4:] == ["--allow-callable", "qa_agent", "--allow-callable", "release_agent"]


def test_container_launch_reuses_workspace_mount_for_nested_app_home(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    app_home = workspace / ".citnega-home"
    app_home.mkdir(parents=True)

    launch = build_remote_worker_container_launch(
        runtime="podman",
        image="ghcr.io/acme/citnega:latest",
        worker_id="worker",
        host="127.0.0.1",
        port=8787,
        allow_callables=["qa_agent"],
        app_home=app_home,
        workspace_root=workspace,
    )

    assert len(launch.mounts) == 1
    assert any(arg == "/workspace/.citnega-home" for arg in launch.command)


def test_container_launch_maps_tls_assets_and_switches_to_https(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    app_home = tmp_path / "app-home"
    app_home.mkdir()
    tls_dir = tmp_path / "tls"
    tls_dir.mkdir()
    cert = tls_dir / "server-cert.pem"
    key = tls_dir / "server-key.pem"
    ca = tls_dir / "ca.pem"
    for path in (cert, key, ca):
        path.write_text("fixture", encoding="utf-8")

    launch = build_remote_worker_container_launch(
        runtime="docker",
        image="ghcr.io/acme/citnega:latest",
        worker_id="worker",
        host="127.0.0.1",
        port=8787,
        allow_callables=["qa_agent"],
        app_home=app_home,
        workspace_root=workspace,
        tls_cert_path=cert,
        tls_key_path=key,
        tls_client_ca_path=ca,
        tls_require_client_cert=True,
    )

    command = list(launch.command)
    assert launch.display_endpoint == "https://127.0.0.1:8787"
    assert "--tls-cert-file" in command
    assert "--tls-key-file" in command
    assert "--tls-client-ca-file" in command
    assert "--tls-require-client-cert" in command
