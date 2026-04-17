"""WelcomeBanner — clean splash shown in the empty chat area on startup."""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static

_LOGO    = "◈  citnega"
_TAGLINE = "agentic  ·  co-partner"
_RULE    = "─" * 32
_HINTS   = [
    "↵  send message",
    "/  slash commands",
    "↑↓ input history",
    "^K open command palette",
    "^Y copy last response",
    "^C quit",
]


class WelcomeBanner(Widget):
    """
    Compact welcome graphic shown when the chat is empty.

    Removed automatically by ``_append_message`` (which removes
    ``#empty-hint`` before mounting the first MessageBlock).
    """

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        width: 1fr;
        align: center middle;
        padding: 4 2;
        content-align: center middle;
    }
    WelcomeBanner #banner-logo {
        color: $accent;
        text-style: bold;
        content-align: center middle;
        width: 1fr;
        height: 1;
        text-style: bold;
    }
    WelcomeBanner #banner-tagline {
        color: $text-muted;
        content-align: center middle;
        width: 1fr;
        height: 1;
        margin-top: 0;
    }
    WelcomeBanner #banner-rule {
        color: $panel-lighten-2;
        content-align: center middle;
        width: 1fr;
        height: 1;
        margin-top: 1;
        margin-bottom: 1;
    }
    WelcomeBanner .banner-hint {
        color: $text-disabled;
        content-align: center middle;
        width: 1fr;
        height: 1;
    }
    """

    def compose(self):
        yield Static(_LOGO,    id="banner-logo",    markup=False)
        yield Static(_TAGLINE, id="banner-tagline", markup=False)
        yield Static(_RULE,    id="banner-rule",    markup=False)
        for hint in _HINTS:
            yield Static(hint, classes="banner-hint", markup=False)
