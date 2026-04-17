"""citnega kb — knowledge base operations."""

from __future__ import annotations

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap
from citnega.packages.kb.ingestion import build_items
from citnega.packages.protocol.models.kb import KBSourceType

app = typer.Typer(help="Knowledge base operations.")


@app.command("add")
@run_async
async def kb_add(
    content: str = typer.Argument(..., help="Text content to add to the KB."),
    title: str = typer.Option("", "--title", "-t", help="Item title (default: first 60 chars)."),
    tag: str = typer.Option("", "--tag", help="Comma-separated tags."),
    source_type: str = typer.Option(
        "document", "--type", help="Source type (document|note|generated)."
    ),
) -> None:
    """Add text to the knowledge base (auto-chunks long content)."""
    resolved_title = title or content[:60].replace("\n", " ") + ("…" if len(content) > 60 else "")
    tags = [t.strip() for t in tag.split(",") if t.strip()] if tag else []

    try:
        stype = KBSourceType(source_type)
    except ValueError:
        typer.echo(
            f"Invalid source type {source_type!r}. Use: document, note, generated.", err=True
        )
        raise typer.Exit(code=1)

    items = build_items(content, title=resolved_title, source_type=stype, tags=tags)

    async with cli_bootstrap() as svc:
        added = 0
        for item in items:
            try:
                await svc.add_kb_item(item)
                added += 1
            except NotImplementedError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2)

    typer.echo(f"Added {added} chunk(s) to the knowledge base.")


@app.command("search")
@run_async
async def kb_search(
    query: str = typer.Argument(..., help="Search query."),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results."),
) -> None:
    """Search the knowledge base using full-text search."""
    async with cli_bootstrap() as svc:
        results = await svc.search_kb(query, limit=limit)
    if not results:
        typer.echo("No KB results.")
        return
    for r in results:
        typer.echo(f"[{r.score:.3f}] {r.item.title[:40]:<40}  {r.snippet[:60]}")


@app.command("export")
@run_async
async def kb_export(
    output: str = typer.Option(
        "", "--output", "-o", help="Output file path (default: timestamped in kb_exports_dir)."
    ),
    fmt: str = typer.Option("jsonl", "--format", "-f", help="Format: jsonl or markdown."),
    session: str = typer.Option(
        "", "--session", "-s",
        help="Limit export to a specific session ID (default: all sessions).",
    ),
) -> None:
    """Export the knowledge base to JSONL or Markdown.

    Use --session <id> to export only items from a specific session.
    Omit --session (or pass 'all') to export the full global KB.
    """
    from pathlib import Path

    fmt_lower = fmt.lower()
    if fmt_lower not in ("jsonl", "markdown"):
        typer.echo(f"Unknown format {fmt!r}. Use: jsonl, markdown.", err=True)
        raise typer.Exit(code=1)

    output_path = Path(output) if output else None
    session_id = session if session else "all"

    async with cli_bootstrap() as svc:
        try:
            path = await svc.export_session(session_id, fmt=fmt_lower, output_path=output_path)
        except NotImplementedError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2)

    scope = f"session {session_id}" if session_id != "all" else "all sessions"
    typer.echo(f"Exported {fmt_lower.upper()} ({scope}) to: {path}")
