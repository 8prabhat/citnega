"""citnega remote — reference remote worker service commands."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap
from citnega.packages.config.loaders import load_settings
from citnega.packages.runtime.remote.container_launcher import (
    build_remote_worker_container_launch,
    run_remote_worker_container,
)
from citnega.packages.runtime.remote.secret_bootstrap import (
    build_remote_secret_bundle,
    default_rotation_key_id,
    render_secret_bundle_json,
    render_secret_bundle_text,
)
from citnega.packages.runtime.remote.service import RemoteWorkerHTTPService
from citnega.packages.storage.path_resolver import PathResolver

app = typer.Typer(help="Reference remote worker service controls.")


@app.command("bootstrap-secrets")
def bootstrap_secrets_command(
    signing_key_id: str = typer.Option(
        default_rotation_key_id(),
        "--signing-key-id",
        help="Active remote envelope signing key id to generate.",
    ),
    include_benchmark_publication_key: bool = typer.Option(
        True,
        "--include-benchmark-publication-key/--no-benchmark-publication-key",
        help="Also generate a signing key for benchmark publication manifests.",
    ),
    benchmark_publication_key_id: str = typer.Option(
        "",
        "--benchmark-publication-key-id",
        help="Override the benchmark publication signing key id.",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text | json.",
    ),
) -> None:
    """Generate rotation-ready secrets for remote workers and benchmark publication."""
    bundle = build_remote_secret_bundle(
        envelope_signing_key_id=signing_key_id,
        include_benchmark_publication_key=include_benchmark_publication_key,
        benchmark_publication_key_id=benchmark_publication_key_id,
    )
    fmt = output_format.strip().lower() or "text"
    if fmt == "json":
        typer.echo(render_secret_bundle_json(bundle))
        return
    if fmt != "text":
        typer.echo("Unsupported format. Expected: text | json.", err=True)
        raise typer.Exit(code=1)
    typer.echo(render_secret_bundle_text(bundle))


@app.command("serve")
@run_async
async def serve_command(
    host: str = typer.Option("", "--host", help="Bind host. Defaults to [remote].service_host."),
    port: int = typer.Option(0, "--port", help="Bind port. Defaults to [remote].service_port."),
    allow_callable: list[str] = typer.Option(
        [],
        "--allow-callable",
        help="Repeatable callable allowlist. Falls back to [remote].allowed_callables.",
    ),
    isolation_profile: str = typer.Option(
        "",
        "--isolation-profile",
        help="Isolation declaration: process | container. Defaults to [remote].service_isolation_profile.",
    ),
    worker_id: str = typer.Option(
        "remote-service-1",
        "--worker-id",
        help="Worker identifier exposed in health/invoke responses.",
    ),
    signing_key: str = typer.Option(
        "",
        "--signing-key",
        help="Override remote envelope signing key. Defaults to [remote].envelope_signing_key.",
    ),
    signing_key_id: str = typer.Option(
        "",
        "--signing-key-id",
        help="Override the active envelope signing key id.",
    ),
    verification_key: list[str] = typer.Option(
        [],
        "--verification-key",
        help="Repeatable accepted verification key entry in the form key_id=secret.",
    ),
    auth_token: str = typer.Option(
        "",
        "--auth-token",
        help="Require bearer token auth for remote dispatch. Defaults to [remote].auth_token.",
    ),
    tls_cert_file: Path | None = typer.Option(
        None,
        "--tls-cert-file",
        help="TLS server certificate PEM file for the reference worker.",
    ),
    tls_key_file: Path | None = typer.Option(
        None,
        "--tls-key-file",
        help="TLS server private key PEM file for the reference worker.",
    ),
    tls_client_ca_file: Path | None = typer.Option(
        None,
        "--tls-client-ca-file",
        help="CA bundle used to verify incoming client certificates.",
    ),
    tls_require_client_cert: bool = typer.Option(
        False,
        "--tls-require-client-cert/--no-tls-require-client-cert",
        help="Require client certificates when the reference worker serves HTTPS.",
    ),
    container_runtime: str = typer.Option(
        "",
        "--container-runtime",
        help="Container runtime for the built-in container launcher (docker | podman).",
    ),
    container_image: str = typer.Option(
        "",
        "--container-image",
        help="Container image for the built-in worker launcher.",
    ),
    container_name: str = typer.Option(
        "",
        "--container-name",
        help="Optional explicit container name for the built-in worker launcher.",
    ),
    app_home: Path | None = typer.Option(
        None,
        "--app-home",
        help="Override app home for configuration and storage.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Override database path used by the worker process.",
    ),
    run_migrations: bool = typer.Option(
        True,
        "--run-migrations/--no-run-migrations",
        help="Run database migrations before serving.",
    ),
) -> None:
    """Run the reference remote worker HTTP service in the foreground."""
    path_resolver = PathResolver(app_home=app_home or (db_path.parent if db_path is not None else None))
    resolved_app_home = path_resolver.app_home
    settings = load_settings(app_home=resolved_app_home)
    effective_host = host.strip() or settings.remote.service_host
    effective_port = int(port) if port > 0 else int(settings.remote.service_port)
    effective_allowlist = [
        item.strip()
        for item in (allow_callable or settings.remote.allowed_callables)
        if item.strip()
    ]
    effective_profile = (
        isolation_profile.strip().lower()
        or settings.remote.service_isolation_profile.strip().lower()
        or "process"
    )
    effective_signing_key = signing_key.strip() or settings.remote.envelope_signing_key.strip()
    effective_signing_key_id = (
        signing_key_id.strip()
        or settings.remote.envelope_signing_key_id.strip()
        or "current"
    )
    effective_verification_keys = [
        item.strip()
        for item in (verification_key or settings.remote.envelope_verification_keys)
        if item.strip()
    ]
    effective_auth_token = auth_token.strip() or settings.remote.auth_token.strip()
    effective_tls_cert_file = (
        str(tls_cert_file).strip()
        if tls_cert_file is not None
        else settings.remote.service_tls_cert_path.strip()
    )
    effective_tls_key_file = (
        str(tls_key_file).strip()
        if tls_key_file is not None
        else settings.remote.service_tls_key_path.strip()
    )
    effective_tls_client_ca_file = (
        str(tls_client_ca_file).strip()
        if tls_client_ca_file is not None
        else settings.remote.service_tls_client_ca_path.strip()
    )
    effective_tls_require_client_cert = (
        bool(tls_require_client_cert)
        or bool(settings.remote.service_tls_require_client_cert)
    )
    effective_container_runtime = (
        container_runtime.strip()
        or settings.remote.service_container_runtime.strip()
        or "docker"
    )
    effective_container_image = (
        container_image.strip()
        or settings.remote.service_container_image.strip()
    )
    effective_container_name = (
        container_name.strip()
        or settings.remote.service_container_name.strip()
    )
    require_signed = bool(settings.remote.require_signed_envelopes)
    in_container = os.environ.get("CITNEGA_REMOTE_IN_CONTAINER", "").strip() == "1"

    if not effective_allowlist:
        typer.echo(
            "Remote worker service requires an explicit allowlist. "
            "Set [remote].allowed_callables or pass --allow-callable.",
            err=True,
        )
        raise typer.Exit(code=1)

    if require_signed and not effective_signing_key:
        typer.echo(
            "Remote worker service requires a signing key when signed envelopes are enabled.",
            err=True,
        )
        raise typer.Exit(code=1)

    if effective_profile == "container" and not in_container:
        try:
            launch = build_remote_worker_container_launch(
                runtime=effective_container_runtime,
                image=effective_container_image,
                worker_id=worker_id,
                host=effective_host,
                port=effective_port,
                allow_callables=effective_allowlist,
                app_home=resolved_app_home,
                workspace_root=Path.cwd(),
                db_path=db_path,
                run_migrations=run_migrations,
                container_name=effective_container_name,
                signing_key=effective_signing_key,
                signing_key_id=effective_signing_key_id,
                verification_keys=effective_verification_keys,
                auth_token=effective_auth_token,
                tls_cert_path=Path(effective_tls_cert_file) if effective_tls_cert_file else None,
                tls_key_path=Path(effective_tls_key_file) if effective_tls_key_file else None,
                tls_client_ca_path=(
                    Path(effective_tls_client_ca_file)
                    if effective_tls_client_ca_file
                    else None
                ),
                tls_require_client_cert=effective_tls_require_client_cert,
            )
            typer.echo(
                f"launching containerized remote worker on {launch.display_endpoint} "
                f"using {launch.runtime}:{launch.image}"
            )
            exit_code = await run_remote_worker_container(launch)
        except (RuntimeError, ValueError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        if exit_code != 0:
            raise typer.Exit(code=exit_code)
        return

    async with cli_bootstrap(
        db_path=db_path,
        app_home=resolved_app_home,
        run_migrations=run_migrations,
    ) as svc:
        worker = RemoteWorkerHTTPService.from_application_service(
            svc,
            signing_key=effective_signing_key,
            signing_key_id=effective_signing_key_id,
            verification_keys=effective_verification_keys,
            allowed_callables=effective_allowlist,
            require_signed_envelopes=require_signed,
            auth_token=effective_auth_token,
            worker_id=worker_id,
            isolation_profile=effective_profile,
            tls_cert_path=effective_tls_cert_file,
            tls_key_path=effective_tls_key_file,
            tls_client_ca_path=effective_tls_client_ca_file,
            tls_require_client_cert=effective_tls_require_client_cert,
        )
        server = worker.create_server(host=effective_host, port=effective_port)
        bound_host, bound_port = server.server_address
        scheme = "https" if worker.tls_enabled else "http"

        typer.echo(f"remote worker listening on {scheme}://{bound_host}:{bound_port}")
        typer.echo(f"health endpoint: {scheme}://{bound_host}:{bound_port}/health")
        typer.echo(f"allowed callables: {', '.join(sorted(worker.allowed_callables))}")
        typer.echo(f"isolation profile: {worker.isolation_profile}")
        typer.echo(f"mTLS required: {'yes' if worker.mtls_required else 'no'}")

        try:
            await asyncio.to_thread(server.serve_forever)
        except (KeyboardInterrupt, asyncio.CancelledError):
            typer.echo("shutting down remote worker", err=True)
        finally:
            server.shutdown()
            server.server_close()
