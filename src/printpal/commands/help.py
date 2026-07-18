"""Help command: /help."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text

from ..ui import console, ACCENT
from . import COMMANDS


def cmd_help() -> None:
    table = Table(show_header=False, box=box.HORIZONTALS, border_style=ACCENT)
    table.add_column("Command", style=f"bold {ACCENT}", width=22)
    table.add_column("Description", style="white")
    display = {k: v for k, v in COMMANDS.items() if k not in {"/clear", "/quit", "/q"}}
    for cmd, desc in display.items():
        table.add_row(cmd, desc)
    console.print(table)
    console.print(Text("Anything else is sent to the agent as a prompt.", style="dim"))
