"""Session management commands: /save, /load, /sessions."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text

from ..ui import console, ACCENT, prompt_yes_no
from .. import db
from ..sessions import next_default_name, save_session, load_session, list_sessions
from .helpers import prompt_save_if_dirty


def cmd_save(
    agent,
    args: list[str],
    model_id: str,
    prompt_history: list[str] | None = None,
    permissions: str = "{}",
) -> bool:
    name = args[0] if args else next_default_name()
    if db.get_session_by_name(name):
        if not prompt_yes_no(f"Session '{name}' exists. Overwrite? [y/N] "):
            return False
    save_session(agent, name, model_id, prompt_history, permissions)
    console.print(Text(f"Saved as '{name}'.", style=f"bold {ACCENT}"))
    return True


def cmd_load(
    agent,
    args: list[str],
    dirty: bool,
    model_id: str,
    prompt_history: list[str] | None = None,
    permissions: str = "{}",
) -> dict:
    """Returns {"loaded": bool, "prompt_history": list[str], "permissions": str}."""
    if not args:
        console.print(
            Text(
                "Usage: /load <name|id>  (e.g. /load batman-print or /load 1)",
                style="dim",
            )
        )
        return {"loaded": False, "prompt_history": [], "permissions": "{}"}
    name_or_id = args[0]
    prompt_save_if_dirty(dirty, agent, model_id, prompt_history, permissions)
    result = load_session(agent, name_or_id)
    if result and result.get("success"):
        loaded_history = result.get("prompt_history", [])
        loaded_perms = result.get("permissions", "{}")
        console.print(
            Text(
                f"Loaded session '{name_or_id}' ({len(agent.memory.steps)} steps).",
                style=f"bold {ACCENT}",
            )
        )
        return {
            "loaded": True,
            "prompt_history": loaded_history,
            "permissions": loaded_perms,
        }
    return {"loaded": False, "prompt_history": [], "permissions": "{}"}


def cmd_sessions() -> None:
    sessions = list_sessions()
    if not sessions:
        console.print(Text("No saved sessions.", style="dim"))
        return
    table = Table(
        show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT
    )
    table.add_column("ID", style="dim", width=5)
    table.add_column("Name", style=f"bold {ACCENT}", min_width=20)
    table.add_column("Steps", justify="right", width=6)
    table.add_column("Model", width=22)
    table.add_column("Updated", style="dim")
    for s in sessions:
        table.add_row(
            str(s["id"]),
            s["name"],
            str(s["step_count"]),
            s["model_id"],
            s["updated_at"],
        )
    console.print(table)
