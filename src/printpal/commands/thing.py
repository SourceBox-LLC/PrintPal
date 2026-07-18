"""Thing management and slice commands: /thing, /slice."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..ui import console, ACCENT, format_size
from .. import db
from .helpers import find_tool, parse_slice_flags


def cmd_thing(args: list[str]) -> None:
    things = db.list_things()
    if not things:
        console.print(Text("No things in database.", style="dim"))
        return
    table = Table(
        show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT
    )
    table.add_column("ID", style="dim", width=5)
    table.add_column("Name", style=f"bold {ACCENT}", min_width=20)
    table.add_column("Type", width=8)
    table.add_column("Size", justify="right", width=10)
    table.add_column("Status", style="dim", width=12)
    table.add_column("From", style="dim", width=8)
    for t in things:
        from_str = f"← #{t['sliced_from']}" if t["sliced_from"] else ""
        table.add_row(
            str(t["id"]),
            t["name"],
            t["file_type"],
            format_size(t["file_size"]),
            t["status"],
            from_str,
        )
    console.print(table)


def cmd_thing_detail(thing_id: int) -> None:
    t = db.get_thing(thing_id)
    if t is None:
        console.print(Text(f"No thing with ID {thing_id}.", style="bold red"))
        return
    lines = [
        Text(f"ID:          {t['id']}", style=f"bold {ACCENT}"),
        Text(f"Name:        {t['name']}"),
        Text(f"Creator:     {t['creator'] or '?'}"),
        Text(f"License:     {t['license'] or '?'}"),
        Text(f"URL:         {t['url'] or '?'}"),
        Text(f"Thingiverse:  {t['thingiverse_id'] or '?'}"),
        Text(f"File:        {t['file_name']}"),
        Text(f"Size:        {format_size(t['file_size'])}"),
        Text(f"Type:        {t['file_type']}"),
        Text(f"Status:      {t['status']}"),
        Text(f"Created:     {t['created_at']}"),
    ]
    if t["sliced_from"]:
        lines.append(Text(f"Sliced from: #{t['sliced_from']}"))
    if t["file_data"] is not None:
        lines.append(
            Text(
                f"In DB:       yes ({format_size(len(t['file_data']))})", style="green"
            )
        )
    else:
        lines.append(Text("In DB:       no", style="red"))
    console.print(
        Panel(
            Text("\n").join(lines),
            title=Text("Thing Details", style="bold"),
            border_style=ACCENT,
        )
    )


def cmd_thing_delete(thing_id: int) -> None:
    t = db.get_thing(thing_id)
    if t is None:
        console.print(Text(f"No thing with ID {thing_id}.", style="bold red"))
        return
    console.print(Text(f"  Name: {t['name']}", style="dim"))
    console.print(Text(f"  File: {t['file_name']}", style="dim"))
    db.delete_thing(thing_id)
    console.print(Text(f"  Removed thing #{thing_id}.", style=f"bold {ACCENT}"))


def cmd_thing_export(thing_id: int, dest: str | None) -> None:
    t = db.get_thing(thing_id)
    if t is None:
        console.print(Text(f"No thing with ID {thing_id}.", style="bold red"))
        return
    if t["file_data"] is None:
        console.print(Text(f"Thing #{thing_id} has no file data.", style="bold red"))
        return
    dest_path = Path(dest) if dest else Path(t["file_name"])
    if dest_path.is_dir():
        dest_path = dest_path / t["file_name"]
    dest_path.write_bytes(t["file_data"])
    console.print(
        Text(
            f"  Exported #{thing_id} to {dest_path} ({format_size(len(t['file_data']))})",
            style=f"bold {ACCENT}",
        )
    )


def cmd_thing_dispatch(args: list[str]) -> None:
    """Dispatch /thing sub-commands."""
    if not args:
        cmd_thing(args)
    elif args[0] == "delete":
        if len(args) < 2:
            console.print(Text("Usage: /thing delete <id>", style="dim"))
        else:
            try:
                cmd_thing_delete(int(args[1]))
            except ValueError:
                console.print(Text("ID must be a number.", style="bold red"))
    elif args[0] == "export":
        if len(args) < 2:
            console.print(Text("Usage: /thing export <id> [dest]", style="dim"))
        else:
            try:
                dest = args[2] if len(args) > 2 else None
                cmd_thing_export(int(args[1]), dest)
            except ValueError:
                console.print(Text("ID must be a number.", style="bold red"))
    elif args[0].isdigit():
        cmd_thing_detail(int(args[0]))
    else:
        console.print(
            Text("Usage: /thing [id|export <id> [dest]|delete <id>]", style="dim")
        )


def cmd_slice(args: list[str], tools: list) -> None:
    if not args:
        console.print(
            Text(
                "Usage: /slice <id> [flags]  (e.g. /slice 1 --layer-height 0.12 --supports)",
                style="dim",
            )
        )
        return
    if not args[0].isdigit():
        console.print(
            Text("First argument must be a thing ID (number).", style="bold red")
        )
        return

    thing_id = int(args[0])
    try:
        flags = parse_slice_flags(args[1:])
    except ValueError as e:
        console.print(Text(str(e), style="bold red"))
        return

    t = db.get_thing(thing_id)
    if t is None:
        console.print(Text(f"No thing with ID {thing_id}.", style="bold red"))
        return
    if t["file_type"] == "gcode":
        console.print(
            Text(
                f"Thing #{thing_id} is already G-code. Use /thing {thing_id} for details.",
                style="dim",
            )
        )
        return
    if t["file_data"] is None:
        console.print(
            Text(
                f"Thing #{thing_id} has no file data in the database.", style="bold red"
            )
        )
        return

    slice_tool = find_tool(tools, "cura_slice_model")
    if slice_tool is None:
        console.print(
            Text(
                "cura_slice_model tool not found. Is PrintMCP running?",
                style="bold red",
            )
        )
        return

    suffix = Path(t["file_name"]).suffix or ".stl"
    console.print(Text(f"Slicing {t['file_name']}...", style=f"bold {ACCENT}"))

    temp_model = None
    temp_gcode = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(t["file_data"])
            temp_model = f.name
        temp_gcode = temp_model + ".gcode"

        tool_kwargs = {
            "model_path": temp_model,
            "response_format": "json",
            "output_path": temp_gcode,
        }
        tool_kwargs.update(flags)

        result = slice_tool.forward(**tool_kwargs)

        if isinstance(result, dict):
            result_data = result
        elif isinstance(result, str):
            try:
                result_data = json.loads(result)
            except json.JSONDecodeError:
                console.print(
                    Text(f"Unexpected tool output: {result[:200]}", style="bold red")
                )
                return
        else:
            console.print(
                Text(f"Unexpected tool output type: {type(result)}", style="bold red")
            )
            return

        gcode_path = result_data.get("gcode_path", temp_gcode)
        gcode_size = result_data.get("gcode_size_bytes", 0)
        stats = result_data.get("stats", {})
        settings = result_data.get("settings", {})

        gcode_bytes = Path(gcode_path).read_bytes()
        gcode_id = db.insert_thing(
            thingiverse_id=t["thingiverse_id"],
            name=t["name"],
            creator=t["creator"],
            license=t["license"],
            url=t["url"],
            file_name=Path(gcode_path).name,
            file_size=len(gcode_bytes),
            file_data=gcode_bytes,
            file_type="gcode",
            sliced_from=thing_id,
            status="sliced",
        )

        lines = [
            Text(
                f"Printer:      {result_data.get('printer', '?')}",
                style=f"bold {ACCENT}",
            ),
            Text(f"G-code:       {Path(gcode_path).name} ({format_size(gcode_size)})"),
        ]
        if stats.get("print_time"):
            lines.append(Text(f"Print time:   {stats['print_time']}"))
        if stats.get("filament_m") is not None:
            vol = f" ({stats['filament_mm3']} mm3)" if stats.get("filament_mm3") else ""
            lines.append(Text(f"Filament:     {stats['filament_m']} m{vol}"))
        lh = settings.get("layer_height", "?")
        inf = settings.get("infill_density", "?")
        sup = "on" if settings.get("supports") else "off"
        lines.append(Text(f"Settings:     {lh}mm, {inf}% infill, supports {sup}"))
        lines.append(
            Text(f"Saved as:     Thing #{gcode_id} (gcode, sliced from #{thing_id})")
        )

        console.print(
            Panel(
                Text("\n").join(lines),
                title=Text(f"Sliced {t['file_name']}", style="bold"),
                border_style=ACCENT,
            )
        )

    except Exception as e:
        console.print(Text(f"Slicing failed: {e}", style="bold red"))
    finally:
        if temp_model:
            try:
                Path(temp_model).unlink(missing_ok=True)
            except OSError:
                pass
        if temp_gcode:
            try:
                Path(temp_gcode).unlink(missing_ok=True)
            except OSError:
                pass
