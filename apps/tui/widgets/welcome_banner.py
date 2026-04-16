"""WelcomeBanner — branded splash shown in the empty chat area on startup."""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

# ── ASCII art logo (ANSI-Shadow block font) ───────────────────────────────────
_LOGO = """\
 ██████╗██╗████████╗███╗  ██╗███████╗ ██████╗  █████╗
██╔════╝██║╚══██╔══╝████╗ ██║██╔════╝██╔════╝ ██╔══██╗
██║     ██║   ██║   ██╔██╗██║█████╗  ██║  ███╗███████║
██║     ██║   ██║   ██║╚████║██╔══╝  ██║   ██║██╔══██║
╚██████╗██║   ██║   ██║ ╚███║███████╗╚██████╔╝██║  ██║
 ╚═════╝╚═╝   ╚═╝   ╚═╝  ╚══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝"""

_TAGLINE = "AGENTIC  :  CO PARTNER"
_RULE    = "─" * 54
_HINT    = "Type a message  ·  / for commands  ·  ↑↓ history"


class WelcomeBanner(Widget):
    """
    Full-page welcome graphic shown when the chat is empty.

    Removed automatically by ``_append_message`` (which removes
    ``#empty-hint`` before mounting the first MessageBlock).
    """

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        width: 1fr;
        align: center middle;
        padding: 3 2;
        content-align: center middle;
    }
    WelcomeBanner #banner-logo {
        color: $accent;
        text-style: bold;
        content-align: center middle;
        width: 1fr;
        height: auto;
    }
    WelcomeBanner #banner-rule-top {
        color: $accent;
        content-align: center middle;
        width: 1fr;
        height: 1;
        margin-top: 1;
    }
    WelcomeBanner #banner-tagline {
        color: $secondary;
        text-style: bold;
        content-align: center middle;
        width: 1fr;
        height: 1;
    }
    WelcomeBanner #banner-rule-bottom {
        color: $accent;
        content-align: center middle;
        width: 1fr;
        height: 1;
        margin-bottom: 2;
    }
    WelcomeBanner #banner-hint {
        color: $text-disabled;
        text-style: italic;
        content-align: center middle;
        width: 1fr;
        height: 1;
    }
    """

    def compose(self):
        yield Static(_LOGO,     id="banner-logo",        markup=False)
        yield Static(_RULE,     id="banner-rule-top",    markup=False)
        yield Static(_TAGLINE,  id="banner-tagline",     markup=False)
        yield Static(_RULE,     id="banner-rule-bottom", markup=False)
        yield Static(_HINT,     id="banner-hint",        markup=False)
