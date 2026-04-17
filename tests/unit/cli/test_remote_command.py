"""Unit tests for the remote worker CLI command."""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from citnega.apps.cli.commands.remote import app


def _settings(
    allowed_callables: list[str] | None = None,
    *,
    isolation_profile: str = "process",
    container_image: str = "",
):
    return SimpleNamespace(
        remote=SimpleNamespace(
            service_host="127.0.0.1",
            service_port=8787,
            service_isolation_profile=isolation_profile,
            allowed_callables=allowed_callables or [],
            envelope_signing_key="secret",
            envelope_signing_key_id="2026-04",
            envelope_verification_keys=["2026-03=old-secret"],
            auth_token="",
            require_signed_envelopes=True,
            service_tls_cert_path="",
            service_tls_key_path="",
            service_tls_client_ca_path="",
            service_tls_require_client_cert=False,
            service_container_runtime="docker",
            service_container_image=container_image,
            service_container_name="",
        )
    )


def _bootstrap_ctx(svc):
    @contextlib.asynccontextmanager
    async def _ctx(**kwargs):
        yield svc

    return _ctx


class _FakeServer:
    def __init__(self) -> None:
        self.server_address = ("127.0.0.1", 9999)
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self) -> None:
        return

    def shutdown(self) -> None:
        self.shutdown_called = True

    def server_close(self) -> None:
        self.closed = True


class _FakeWorker:
    def __init__(self, *, tls_enabled: bool = False, mtls_required: bool = False) -> None:
        self.allowed_callables = frozenset({"qa_agent"})
        self.isolation_profile = "process"
        self.tls_enabled = tls_enabled
        self.mtls_required = mtls_required
        self.server = _FakeServer()

    def create_server(self, *, host: str, port: int):
        return self.server


class _FakeLaunch:
    runtime = "docker"
    image = "ghcr.io/acme/citnega:latest"
    display_endpoint = "http://127.0.0.1:8787"


class TestRemoteServeCommand:
    def test_remote_bootstrap_secrets_supports_json_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["bootstrap-secrets", "--signing-key-id", "2026-04", "--format", "json"])

        assert result.exit_code == 0
        assert '"envelope_signing_key_id": "2026-04"' in result.output
        assert '"benchmark_publication"' in result.output

    def test_remote_serve_requires_allowlist(self) -> None:
        runner = CliRunner()
        with (
            patch("citnega.apps.cli.commands.remote.PathResolver", return_value=SimpleNamespace(app_home=Path("/tmp/citnega-app"))),
            patch("citnega.apps.cli.commands.remote.load_settings", return_value=_settings([])),
        ):
            result = runner.invoke(app, ["serve"])

        assert result.exit_code == 1
        assert "requires an explicit allowlist" in result.output

    def test_remote_serve_prints_bound_endpoint(self) -> None:
        runner = CliRunner()
        fake_worker = _FakeWorker()
        fake_service = object()
        with (
            patch("citnega.apps.cli.commands.remote.PathResolver", return_value=SimpleNamespace(app_home=Path("/tmp/citnega-app"))),
            patch("citnega.apps.cli.commands.remote.load_settings", return_value=_settings(["qa_agent"])),
            patch("citnega.apps.cli.commands.remote.cli_bootstrap", _bootstrap_ctx(fake_service)),
            patch(
                "citnega.apps.cli.commands.remote.RemoteWorkerHTTPService.from_application_service",
                return_value=fake_worker,
            ),
        ):
            result = runner.invoke(app, ["serve", "--allow-callable", "qa_agent"])

        assert result.exit_code == 0
        assert "remote worker listening on http://127.0.0.1:9999" in result.output
        assert "allowed callables: qa_agent" in result.output
        assert fake_worker.server.shutdown_called is True
        assert fake_worker.server.closed is True

    def test_remote_serve_prints_https_when_tls_enabled(self) -> None:
        runner = CliRunner()
        fake_worker = _FakeWorker(tls_enabled=True, mtls_required=True)
        fake_service = object()
        with (
            patch("citnega.apps.cli.commands.remote.PathResolver", return_value=SimpleNamespace(app_home=Path("/tmp/citnega-app"))),
            patch("citnega.apps.cli.commands.remote.load_settings", return_value=_settings(["qa_agent"])),
            patch("citnega.apps.cli.commands.remote.cli_bootstrap", _bootstrap_ctx(fake_service)),
            patch(
                "citnega.apps.cli.commands.remote.RemoteWorkerHTTPService.from_application_service",
                return_value=fake_worker,
            ),
        ):
            result = runner.invoke(app, ["serve", "--allow-callable", "qa_agent"])

        assert result.exit_code == 0
        assert "remote worker listening on https://127.0.0.1:9999" in result.output
        assert "mTLS required: yes" in result.output

    def test_remote_serve_launches_container_when_container_profile_selected(self) -> None:
        runner = CliRunner()
        launch = _FakeLaunch()
        with (
            patch("citnega.apps.cli.commands.remote.PathResolver", return_value=SimpleNamespace(app_home=Path("/tmp/citnega-app"))),
            patch(
                "citnega.apps.cli.commands.remote.load_settings",
                return_value=_settings(
                    ["qa_agent"],
                    isolation_profile="container",
                    container_image=launch.image,
                ),
            ),
            patch(
                "citnega.apps.cli.commands.remote.build_remote_worker_container_launch",
                return_value=launch,
            ) as build_launch,
            patch(
                "citnega.apps.cli.commands.remote.run_remote_worker_container",
                AsyncMock(return_value=0),
            ) as run_launch,
            patch(
                "citnega.apps.cli.commands.remote.RemoteWorkerHTTPService.from_application_service"
            ) as create_worker,
        ):
            result = runner.invoke(app, ["serve", "--allow-callable", "qa_agent"])

        assert result.exit_code == 0
        assert "launching containerized remote worker on http://127.0.0.1:8787" in result.output
        build_launch.assert_called_once()
        run_launch.assert_awaited_once_with(launch)
        create_worker.assert_not_called()

    def test_remote_serve_container_profile_requires_image(self) -> None:
        runner = CliRunner()
        with (
            patch("citnega.apps.cli.commands.remote.PathResolver", return_value=SimpleNamespace(app_home=Path("/tmp/citnega-app"))),
            patch(
                "citnega.apps.cli.commands.remote.load_settings",
                return_value=_settings(["qa_agent"], isolation_profile="container", container_image=""),
            ),
        ):
            result = runner.invoke(app, ["serve", "--allow-callable", "qa_agent"])

        assert result.exit_code == 1
        assert "Container image is required" in result.output
