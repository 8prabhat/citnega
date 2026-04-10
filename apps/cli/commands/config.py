"""citnega config — validate or display application configuration."""

from __future__ import annotations

import json

import typer

app = typer.Typer(help="Validate or display configuration.")


@app.command("validate")
def config_validate() -> None:
    """Load and validate settings; print any errors."""
    try:
        from citnega.packages.config.loaders import load_settings  # noqa: PLC0415
        settings = load_settings()
        typer.echo("Configuration is valid.")
        typer.echo(f"  log_level:  {settings.logging.level}")
        typer.echo(f"  framework:  {settings.runtime.framework}")
        typer.echo(f"  model:      {settings.runtime.default_model_id}")
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("show")
def config_show(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Display the resolved configuration."""
    try:
        from citnega.packages.config.loaders import load_settings  # noqa: PLC0415
        settings = load_settings()
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(
            json.dumps(settings.model_dump(), default=str, indent=2)
        )
    else:
        _print_section("runtime",  settings.runtime.model_dump())
        _print_section("session",  settings.session.model_dump())
        _print_section("logging",  settings.logging.model_dump())
        _print_section("context",  settings.context.model_dump())
        _print_section("security", settings.security.model_dump())


def _print_section(name: str, data: dict) -> None:
    typer.echo(f"\n[{name}]")
    for k, v in data.items():
        typer.echo(f"  {k} = {v}")
