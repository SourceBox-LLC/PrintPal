"""Shared UI constants and helpers for PrintPal.

All modules import ``console`` and ``ACCENT`` from here. Do not create new
``Console`` instances elsewhere.
"""

from __future__ import annotations

from rich.console import Console

# Matches smolagents' YELLOW_HEX for visual consistency.
ACCENT = "#d4b702"

# Shared console instance — highlight=False prevents Rich from colorizing
# arbitrary text that happens to look like markup.
console = Console(highlight=False)

# ASCII art logo for the banner
LOGO = r"""
 ██████╗ ██████╗ ██╗███╗   ██╗████████╗██████╗  █████╗ ██╗
 ██╔══██╗██╔══██╗██║████╗  ██║╚══██╔══╝██╔══██╗██╔══██╗██║
 ██████╔╝██████╔╝██║██╔██╗ ██║   ██║   ██████╔╝███████║██║
 ██╔═══╝ ██╔══██╗██║██║╚██╗██║   ██║   ██╔═══╝ ██╔══██║██║
 ██║     ██║  ██║██║██║ ╚████║   ██║   ██║     ██║  ██║███████╗
 ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝╚══════╝
        ⬡ ⬡ ⬡  download · slice · print · repeat  ⬡ ⬡ ⬡


"""


def prompt_yes_no(prompt: str) -> bool:
    """Ask a yes/no question on stdin. Returns False on anything that isn't y/yes."""
    try:
        response = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return response in {"y", "yes"}


def format_size(size_bytes: int | None) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes is None:
        return "?"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def format_duration(seconds: float | None) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds is None:
        return "?"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def make_bar(filled: float, total: float, width: int = 16) -> str:
    """Create a visual progress bar string like [████████░░░░░░░░].

    Args:
        filled: How much is filled.
        total: The maximum capacity.
        width: Number of characters in the bar.
    """
    if total <= 0:
        return "[" + "░" * width + "]"
    pct = min(1.0, filled / total)
    filled_chars = int(pct * width)
    return "[" + "█" * filled_chars + "░" * (width - filled_chars) + "]"


def format_tokens(tokens: int) -> str:
    """Format a token count as a compact string (e.g. 15.2k, 1.4M)."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k"
    return str(tokens)
