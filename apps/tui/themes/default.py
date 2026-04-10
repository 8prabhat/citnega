"""
Default dark and light theme CSS variable overrides for Citnega TUI.

These strings are loaded via ``app.stylesheet.read_string(theme)``
in CitnegaApp.on_mount().  They override Textual's built-in design
tokens for a consistent look without a separate .tcss file.
"""

from __future__ import annotations

DARK_THEME: str = """
/* Citnega dark theme — extends Textual default dark */
$background:          #0d1117;
$surface:             #161b22;
$panel:               #21262d;
$boost:               #1c2128;
$panel-lighten-1:     #30363d;

$primary:             #388bfd;
$primary-darken-1:    #1f6feb;
$secondary:           #8b949e;

$accent:              #388bfd;
$success:             #3fb950;
$warning:             #d29922;
$error:               #f85149;

$text:                #e6edf3;
$text-muted:          #8b949e;
$text-disabled:       #484f58;
"""

LIGHT_THEME: str = """
/* Citnega light theme — extends Textual default light */
$background:          #ffffff;
$surface:             #f6f8fa;
$panel:               #eaeef2;
$boost:               #f0f6ff;
$panel-lighten-1:     #d0d7de;

$primary:             #0969da;
$primary-darken-1:    #0550ae;
$secondary:           #57606a;

$accent:              #0969da;
$success:             #1a7f37;
$warning:             #9a6700;
$error:               #cf222e;

$text:                #1f2328;
$text-muted:          #57606a;
$text-disabled:       #8c959f;
"""
