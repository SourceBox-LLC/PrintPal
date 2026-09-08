"""Admin commands: /config, /cost, /logs, /backup, /self-destruct."""

from __future__ import annotations

import shutil

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .. import db
from ..pricing import MASKED_KEYS, MODEL_PRICING, RESTART_KEYS
from ..ui import ACCENT, console, format_size, make_bar, prompt_yes_no


def cmd_config(args: list[str]) -> None:
    """Show or set app settings."""
    if not args:
        settings = db.get_all_settings()
        if not settings:
            console.print(
                Text(
                    "No settings configured. Use /config set <key> <value> to set one.",
                    style="dim",
                )
            )
            return
        table = Table(
            show_header=True,
            header_style="bold",
            box=box.HORIZONTALS,
            border_style=ACCENT,
        )
        table.add_column("Key", style=f"bold {ACCENT}", width=20)
        table.add_column("Value", width=40)
        for key in sorted(settings.keys()):
            value = settings[key]
            if key in MASKED_KEYS and value:
                value = "****"
            table.add_row(key, value)
        console.print(table)
        console.print(
            Text(
                "  Configurable: octoprint_url, octoprint_api_key, thingiverse_token, cura_dir, auto_save",
                style="dim",
            )
        )
        return

    sub = args[0].lower()
    if sub == "set":
        if len(args) < 3:
            console.print(Text("Usage: /config set <key> <value>", style="dim"))
            return
        key = args[1]
        value = " ".join(args[2:])
        db.set_setting(key, value)
        db.log_message("INFO", f"Setting '{key}' changed")
        console.print(
            Text(
                f"  Set {key} = {value if key not in MASKED_KEYS else '****'}",
                style=f"bold {ACCENT}",
            )
        )
        if key in RESTART_KEYS:
            console.print(Text("  Restart PrintPal to apply this setting.", style="yellow"))

    elif sub == "get":
        if len(args) < 2:
            console.print(Text("Usage: /config get <key>", style="dim"))
            return
        key = args[1]
        value = db.get_setting(key)
        if value is not None:
            console.print(Text(f"  {key} = {value}", style=f"bold {ACCENT}"))
        else:
            console.print(Text(f"  {key} is not set", style="dim"))

    elif sub == "unset":
        if len(args) < 2:
            console.print(Text("Usage: /config unset <key>", style="dim"))
            return
        key = args[1]
        if db.delete_setting(key):
            db.log_message("INFO", f"Setting '{key}' removed")
            console.print(Text(f"  Removed {key}", style=f"bold {ACCENT}"))
        else:
            console.print(Text(f"  {key} was not set", style="dim"))

    else:
        console.print(Text("Usage: /config [set <key> <value>|get <key>|unset <key>]", style="dim"))


def cmd_cost(agent, model_id: str) -> None:
    """Show token usage and estimated cost for this session."""
    try:
        usage = agent.monitor.get_total_token_counts()
    except Exception:
        usage = None

    if usage is None:
        console.print(Text("No token usage data available.", style="dim"))
        return

    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    total_tokens = input_tokens + output_tokens

    pricing = MODEL_PRICING.get(model_id, {"input": 0, "output": 0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    step_count = len(agent.memory.steps)
    max_tokens = max(input_tokens, output_tokens, 1)

    lines = [
        Text(f"Model:    {model_id}", style=f"bold {ACCENT}"),
        Text(f"Steps:    {step_count}"),
        Text(""),
        Text(
            f"Input:    {input_tokens:,} tokens  {make_bar(input_tokens, max_tokens, 16)}  ${input_cost:.4f}"
        ),
        Text(
            f"Output:   {output_tokens:,} tokens  {make_bar(output_tokens, max_tokens, 16)}  ${output_cost:.4f}"
        ),
        Text(""),
        Text(f"Total:    {total_tokens:,} tokens  ${total_cost:.4f}", style="bold"),
    ]

    if model_id not in MODEL_PRICING:
        lines.append(Text(""))
        lines.append(
            Text(
                "Pricing not available for this model — cost estimate is $0.",
                style="dim",
            )
        )

    console.print(
        Panel(
            Text("\n").join(lines),
            title=Text("Session Cost", style="bold"),
            border_style=ACCENT,
        )
    )


def cmd_logs(args: list[str]) -> None:
    """Show or clear logs."""
    if args and args[0].lower() == "clear":
        count = db.clear_logs()
        console.print(Text(f"  Cleared {count} log entries.", style=f"bold {ACCENT}"))
        return

    limit = 20
    level = None

    if args:
        if args[0].lower() in {"error", "warning", "info"}:
            level = args[0].upper()
        elif args[0].isdigit():
            limit = int(args[0])

    logs = db.get_logs(limit=limit, level=level)
    if not logs:
        console.print(Text("No log entries.", style="dim"))
        return

    table = Table(show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Level", width=8)
    table.add_column("Message", min_width=30)
    table.add_column("Time", style="dim", width=20)

    for log in logs:
        level_str = log["level"]
        level_style = (
            "bold red" if level_str == "ERROR" else "yellow" if level_str == "WARNING" else "dim"
        )
        table.add_row(
            str(log["id"]),
            Text(level_str, style=level_style),
            log["message"],
            log["created_at"],
        )

    console.print(table)


def cmd_backup(args: list[str]) -> None:
    """Create or manage DB backups."""
    if args and args[0].lower() == "list":
        backups = db.list_backups()
        if not backups:
            console.print(Text("No backups found.", style="dim"))
            return
        table = Table(
            show_header=True,
            header_style="bold",
            box=box.HORIZONTALS,
            border_style=ACCENT,
        )
        table.add_column("Name", style=f"bold {ACCENT}", min_width=30)
        table.add_column("Size", justify="right", width=12)
        table.add_column("Modified", style="dim", width=22)
        for b in backups:
            table.add_row(b["name"], format_size(b["size"]), b["modified"])
        console.print(table)
        return

    if args and args[0].lower() == "restore":
        if len(args) < 2:
            console.print(Text("Usage: /backup restore <filename>", style="dim"))
            return
        filename = args[1]
        if not prompt_yes_no(
            f"Restore '{filename}'? This will overwrite the current database. [y/N] "
        ):
            return
        if db.restore_backup(filename):
            db.log_message("INFO", f"Restored from backup: {filename}")
            console.print(
                Text(
                    f"  Restored from {filename}. Restart PrintPal to use the restored data.",
                    style=f"bold {ACCENT}",
                )
            )
        else:
            console.print(Text(f"  Backup '{filename}' not found.", style="bold red"))
        return

    name = db.create_backup()
    db.log_message("INFO", f"Backup created: {name}")
    console.print(Text(f"  Backup created: {name}", style=f"bold {ACCENT}"))


# ---------------------------------------------------------------------------
# Self-destruct command
# ---------------------------------------------------------------------------


def cmd_self_destruct() -> bool:
    """Delete everything — the database, backups, and all PrintPal data.

    Returns True if the user confirmed and destruction was carried out.
    The caller should exit the app after this returns True.
    """
    from pathlib import Path

    console.print(
        Panel(
            Text(
                "\U0001f6a9 \u26a0  SELF-DESTRUCT  \u26a0 \U0001f6a9\n\n"
                "This will permanently delete:\n"
                "  \u2022 The entire database (sessions, things, settings, logs)\n"
                "  \u2022 All database backups\n"
                "  \u2022 The ~/.printpal/ directory\n\n"
                "This action is IRREVERSIBLE.\n"
                "All downloaded models, sliced G-code, and saved sessions will be gone forever.",
                style="bold red",
            ),
            title=Text("\u26a0  SELF-DESTRUCT  \u26a0", style="bold red"),
            border_style="red",
        )
    )

    if not prompt_yes_no("Are you absolutely sure? [y/N] "):
        console.print(Text("Self-destruct aborted.", style="dim"))
        return False

    # Second confirmation — type "DELETE" to proceed
    console.print(Text('Type "DELETE" to confirm: ', style="bold red"), end="")
    try:
        confirmation = input().strip()
    except (EOFError, KeyboardInterrupt):
        console.print(Text("\nSelf-destruct aborted.", style="dim"))
        return False

    if confirmation != "DELETE":
        console.print(Text("Confirmation did not match. Self-destruct aborted.", style="dim"))
        return False

    # Delete everything
    printpal_dir = Path.home() / ".printpal"

    try:
        if printpal_dir.exists():
            shutil.rmtree(str(printpal_dir))
        console.print(Text("  All PrintPal data has been permanently deleted.", style="bold red"))
        return True
    except Exception as e:
        console.print(Text(f"  Error during deletion: {e}", style="bold red"))
        return False
