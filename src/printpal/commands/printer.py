"""Printer preset commands: /printer [list|use|show|add|remove].

Printers are named bundles of slicer settings (Cura printer id + OrcaSlicer
machine/process/filament presets). `/printer use <name>` applies the bundle into
the active settings so `/slice` and the agent slice for that printer.
"""

from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .. import db
from ..config import ORCA_DEFAULTS
from ..ui import ACCENT, console, prompt_yes_no

_USAGE = (
    "Usage: /printer [list|show <name>|use <name>|add <name> [opts]|remove <name>]\n"
    "  add options: --cura <cura_printer_id>  --machine <orca_machine>  "
    "--process <orca_process>  --filament <orca_filament>"
)


def cmd_printer(args: list[str]) -> None:
    """Dispatch /printer sub-commands."""
    if not args or args[0] == "list":
        _list()
    elif args[0] == "use":
        _use(args[1:])
    elif args[0] == "show":
        _show(args[1:])
    elif args[0] == "add":
        _add(args[1:])
    elif args[0] == "remove" or args[0] == "delete":
        _remove(args[1:])
    else:
        console.print(Text(_USAGE, style="dim"))


def _list() -> None:
    printers = db.list_printers()
    active = db.get_active_printer()
    active_name = active["name"] if active else None

    if not printers:
        console.print(Text("No printer presets. Add one with /printer add.", style="dim"))
        return

    table = Table(show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT)
    table.add_column("", width=2)  # active marker
    table.add_column("Name", style=f"bold {ACCENT}", min_width=14)
    table.add_column("Cura printer", style="dim")
    table.add_column("Orca machine", style="dim")
    for p in printers:
        marker = "●" if p["name"] == active_name else ""
        table.add_row(marker, p["name"], p["cura_printer"] or "—", p["orca_machine"] or "—")
    console.print(table)
    if active_name:
        console.print(Text(f"  active: {active_name}", style="dim"))
    else:
        console.print(Text("  none active — /printer use <name> to select one", style="dim"))


def _name_from_args(args: list[str]) -> str:
    """Printer names from the REPL may be unquoted multi-word (e.g.
    `/printer use voron 2.4`). Join args with spaces; shlex already stripped
    any quotes the user typed, so both `/printer use "voron 2.4"` and the bare
    form land here the same way."""
    return " ".join(args).strip()


def _show(args: list[str]) -> None:
    name = _name_from_args(args)
    if not name:
        active = db.get_active_printer()
        if active is None:
            console.print(
                Text("No active printer. /printer use <name> to select one.", style="dim")
            )
            return
        p = active
    else:
        p = db.get_printer(name)
        if p is None:
            console.print(Text(f"No printer preset '{name}'.", style="bold red"))
            return

    active = db.get_active_printer()
    is_active = active is not None and active["name"].lower() == p["name"].lower()
    lines = [
        Text(
            f"Name:         {p['name']}{'  (active)' if is_active else ''}", style=f"bold {ACCENT}"
        ),
        Text(f"Cura printer: {p['cura_printer'] or '—'}"),
        Text(f"Orca machine: {p['orca_machine'] or '—'}"),
        Text(f"Orca process: {p['orca_process'] or '—'}"),
        Text(f"Orca filament:{(' ' + p['orca_filament']) if p['orca_filament'] else ' —'}"),
    ]
    console.print(
        Panel(Text("\n").join(lines), title=Text("Printer", style="bold"), border_style=ACCENT)
    )


def _use(args: list[str]) -> None:
    name = _name_from_args(args)
    if not name:
        console.print(Text("Usage: /printer use <name>", style="dim"))
        return
    applied = db.use_printer(name)
    if applied is None:
        near = ", ".join(p["name"] for p in db.list_printers()) or "(none)"
        console.print(Text(f"No printer preset '{name}'. Available: {near}", style="bold red"))
        return
    console.print(Text(f"Active printer: {applied['name']}", style=f"bold {ACCENT}"))
    console.print(Text(f"  Orca machine:  {applied['orca_machine'] or '—'}", style="dim"))
    console.print(Text(f"  Orca process:  {applied['orca_process'] or '—'}", style="dim"))
    console.print(Text(f"  Orca filament: {applied['orca_filament'] or '—'}", style="dim"))
    console.print(Text(f"  Cura printer:  {applied['cura_printer'] or '—'}", style="dim"))


def _parse_add_opts(args: list[str]) -> tuple[str, dict[str, str]]:
    """Parse `/printer add <name> --cura X --machine Y --process Z --filament W`."""
    if not args:
        raise ValueError("Usage: /printer add <name> [options]")
    name = args[0]
    opts = {"cura": "", "machine": "", "process": "", "filament": ""}
    flagmap = {
        "--cura": "cura",
        "--machine": "machine",
        "--process": "process",
        "--filament": "filament",
    }
    i = 1
    while i < len(args):
        flag = args[i]
        if flag not in flagmap:
            raise ValueError(f"Unknown option: {flag}")
        if i + 1 >= len(args):
            raise ValueError(f"Missing value for {flag}")
        opts[flagmap[flag]] = args[i + 1]
        i += 2
    return name, opts


def _add(args: list[str]) -> None:
    try:
        name, opts = _parse_add_opts(args)
    except ValueError as e:
        console.print(Text(str(e), style="bold red"))
        console.print(Text(_USAGE, style="dim"))
        return

    # Pre-fill from the Ender-3 Pro defaults so a bare `/printer add voron`
    # still yields a working (if generic) starting point; the user refines it.
    db.upsert_printer(
        name,
        cura_printer=opts["cura"] or "creality_ender3pro",
        orca_machine=opts["machine"] or ORCA_DEFAULTS["orca_machine"],
        orca_process=opts["process"] or ORCA_DEFAULTS["orca_process"],
        orca_filament=opts["filament"] or ORCA_DEFAULTS["orca_filament"],
    )
    console.print(Text(f"Saved printer preset '{name}'.", style=f"bold {ACCENT}"))
    console.print(Text(f"  Activate it with: /printer use {name}", style="dim"))


def _remove(args: list[str]) -> None:
    name = _name_from_args(args)
    if not name:
        console.print(Text("Usage: /printer remove <name>", style="dim"))
        return
    if db.get_printer(name) is None:
        console.print(Text(f"No printer preset '{name}'.", style="bold red"))
        return
    if not prompt_yes_no(f"Remove printer preset '{name}'? [y/N] "):
        console.print(Text("Cancelled.", style="dim"))
        return
    # Capture whether this preset is active BEFORE deleting it (after delete,
    # get_active_printer() can no longer resolve the name back to a row).
    active_before = db.get_active_printer()
    was_active = active_before is not None and active_before["name"].lower() == name.lower()

    if db.delete_printer(name):
        # If it was active, clear the active pointer AND the settings it had
        # applied so slicing falls back to defaults/remaining printers instead
        # of a phantom preset.
        if was_active:
            db.delete_setting("active_printer")
            for k in ("orca_machine", "orca_process", "orca_filament", "cura_printer"):
                db.delete_setting(k)
        console.print(Text(f"Removed printer preset '{name}'.", style=f"bold {ACCENT}"))
    else:
        console.print(Text(f"No printer preset '{name}'.", style="bold red"))
