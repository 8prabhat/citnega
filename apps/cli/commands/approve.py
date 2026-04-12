"""citnega approve — respond to a pending tool-execution approval request."""

from __future__ import annotations

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap

app = typer.Typer(help="Respond to a pending approval request.")


@app.command("approve")
@run_async
async def approve_command(
    approval_id: str = typer.Argument(..., help="Approval ID to resolve."),
    deny: bool = typer.Option(False, "--deny", "-d", help="Deny instead of approve."),
    note: str = typer.Option("", "--note", "-n", help="Optional note to record."),
) -> None:
    """
    Approve or deny a pending callable execution request.

    Prints the resolved status to stdout.
    """
    approved = not deny
    async with cli_bootstrap() as svc:
        try:
            await svc.respond_to_approval(
                approval_id,
                approved=approved,
                note=note or None,
            )
        except Exception as exc:
            typer.echo(f"Error resolving approval {approval_id!r}: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    action = "approved" if approved else "denied"
    typer.echo(f"Approval {approval_id} {action}.")
