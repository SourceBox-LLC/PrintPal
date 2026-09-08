"""Thing management and slice commands: /thing, /slice."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .. import db
from ..config import ORCA_DEFAULTS, ORCA_FLAG_OVERRIDES
from ..ui import ACCENT, console, format_size
from .helpers import find_tool, parse_slice_flags


def cmd_thing(args: list[str]) -> None:
    things = db.list_things()
    if not things:
        console.print(Text("No things in database.", style="dim"))
        return
    table = Table(show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT)
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
        lines.append(Text(f"In DB:       yes ({format_size(len(t['file_data']))})", style="green"))
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
        console.print(Text("Usage: /thing [id|export <id> [dest]|delete <id>]", style="dim"))


def cmd_slice(args: list[str], tools: list) -> None:
    if not args:
        console.print(
            Text(
                "Usage: /slice <id> [flags]  (e.g. /slice 1 --layer-height 0.12 --supports)\n"
                "  Slicers: auto-detects Cura or OrcaSlicer. Force one with --slicer cura|orca.",
                style="dim",
            )
        )
        return
    if not args[0].isdigit():
        console.print(Text("First argument must be a thing ID (number).", style="bold red"))
        return

    thing_id = int(args[0])
    try:
        flags = parse_slice_flags(args[1:])
    except ValueError as e:
        console.print(Text(str(e), style="bold red"))
        return

    # Pop the control key (not a tool kwarg). --slicer cura|orca forces a backend.
    slicer_pref = (
        flags.pop("_slicer", None) or db.get_setting("slicer") or ORCA_DEFAULTS["slicer"]
    ).lower()
    if slicer_pref not in ("auto", "cura", "orca"):
        console.print(Text(f"Unknown slicer '{slicer_pref}' (use cura or orca).", style="bold red"))
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
            Text(f"Thing #{thing_id} has no file data in the database.", style="bold red")
        )
        return

    # Choose a backend. orca is preferred in auto mode when the tool is present.
    cura_tool = find_tool(tools, "cura_slice_model")
    orca_tool = find_tool(tools, "orca_slice_model")
    if slicer_pref == "cura":
        backend = "cura"
    elif slicer_pref == "orca":
        backend = "orca"
    else:  # auto
        backend = "orca" if orca_tool is not None else "cura"

    if backend == "cura":
        if cura_tool is None:
            console.print(
                Text(
                    "cura_slice_model tool not found. Is PrintMCP running?",
                    style="bold red",
                )
            )
            return
        _slice_via_cura(t, thing_id, flags, cura_tool)
    else:
        if orca_tool is None:
            console.print(
                Text(
                    "orca_slice_model tool not found. Is OrcaSlicer installed and PrintMCP running?",
                    style="bold red",
                )
            )
            return
        _slice_via_orca(t, thing_id, flags, orca_tool)


def _tool_result_to_dict(result):
    """Normalize a smolagents tool forward() result to a dict (or None).

    Handles dicts, JSON strings, and Pydantic models (``model_dump``) — the last
    covers direct in-process calls where the MCP JSON serialization is skipped.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            return dumped if isinstance(dumped, dict) else None
        except (TypeError, ValueError, RuntimeError):
            return None
    return None


def _render_slice_result(t, thing_id: int, result_data: dict, title: str, temp_gcode: str) -> None:
    """Shared: read the produced G-code into the DB and show a result panel."""
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

    lines = []
    printer = result_data.get("printer") or settings.get("machine")
    if printer:
        lines.append(Text(f"Printer:      {printer}", style=f"bold {ACCENT}"))
    lines.append(Text(f"G-code:       {Path(gcode_path).name} ({format_size(gcode_size)})"))
    if stats.get("print_time"):
        lines.append(Text(f"Print time:   {stats['print_time']}"))
    if stats.get("filament_m") is not None:
        vol = f" ({stats['filament_mm3']} mm3)" if stats.get("filament_mm3") else ""
        lines.append(Text(f"Filament:     {stats['filament_m']} m{vol}"))
    # Cura settings carry layer_height/infill/supports; Orca settings carry machine/process/filament.
    if "layer_height" in settings or "infill_density" in settings:
        lh = settings.get("layer_height", "?")
        inf = settings.get("infill_density", "?")
        sup = "on" if settings.get("supports") else "off"
        lines.append(Text(f"Settings:     {lh}mm, {inf}% infill, supports {sup}"))
    elif settings.get("process"):
        lines.append(Text(f"Process:      {settings['process']}"))
        if settings.get("filament"):
            lines.append(Text(f"Filament:     {settings['filament']}"))
    lines.append(Text(f"Saved as:     Thing #{gcode_id} (gcode, sliced from #{thing_id})"))

    console.print(
        Panel(
            Text("\n").join(lines),
            title=Text(title, style="bold"),
            border_style=ACCENT,
        )
    )


def _slice_via_cura(t, thing_id: int, flags: dict, slice_tool) -> None:
    """Slice with CuraEngine (the original backend)."""
    suffix = Path(t["file_name"]).suffix or ".stl"
    console.print(Text(f"Slicing {t['file_name']} (Cura)...", style=f"bold {ACCENT}"))

    # Printer: user flag -> active printer preset's cura_printer -> tool default.
    if "printer" not in flags:
        active = db.get_active_printer()
        cura_printer = (active or {}).get("cura_printer") or db.get_setting("cura_printer")
        if cura_printer:
            flags["printer"] = cura_printer

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
        result_data = _tool_result_to_dict(result)
        if result_data is None:
            console.print(Text(f"Unexpected tool output: {str(result)[:200]}", style="bold red"))
            return
        _render_slice_result(
            t, thing_id, result_data, f"Sliced {t['file_name']} (Cura)", temp_gcode
        )
    except Exception as e:
        console.print(Text(f"Slicing failed: {e}", style="bold red"))
    finally:
        for p in (temp_model, temp_gcode):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass


def _slice_via_orca(t, thing_id: int, flags: dict, orca_tool) -> None:
    """Slice with OrcaSlicer's CLI using its 3-tier presets (machine/process/filament)."""
    suffix = Path(t["file_name"]).suffix or ".stl"
    console.print(Text(f"Slicing {t['file_name']} (OrcaSlicer)...", style=f"bold {ACCENT}"))

    # Presets: active printer preset -> DB settings -> defaults. This lets
    # /printer use <name> drive slicing, while /config set orca_* still works.
    active = db.get_active_printer()
    machine = (
        (active or {}).get("orca_machine")
        or db.get_setting("orca_machine")
        or ORCA_DEFAULTS["orca_machine"]
    )
    process = (
        (active or {}).get("orca_process")
        or db.get_setting("orca_process")
        or ORCA_DEFAULTS["orca_process"]
    )
    filament = (
        (active or {}).get("orca_filament")
        or db.get_setting("orca_filament")
        or ORCA_DEFAULTS["orca_filament"]
    )

    # Map user-set simple flags to Orca overrides (only flags actually passed).
    overrides = {ORCA_FLAG_OVERRIDES[k]: v for k, v in flags.items() if k in ORCA_FLAG_OVERRIDES}
    if "sparse_infill_density" in overrides:
        overrides["sparse_infill_density"] = f"{overrides['sparse_infill_density']}%"
    if flags.get("supports"):
        overrides["enable_support"] = True
    # Map the unified adhesion keyword to Orca's actual settings (Orca has no
    # single "adhesion_type" — it splits across brim_width / raft_layers /
    # skirt_loops). Only applies a non-default footprint; "skirt" (the default)
    # is already what the presets use, so we leave it alone.
    adhesion = (flags.get("adhesion_type") or "").lower()
    if adhesion == "brim":
        overrides["brim_width"] = "5"
        overrides["skirt_loops"] = "0"
    elif adhesion == "raft":
        overrides["raft_layers"] = "3"
        overrides["skirt_loops"] = "0"
        overrides["brim_width"] = "0"
    elif adhesion == "none":
        overrides["skirt_loops"] = "0"
        overrides["brim_width"] = "0"
        overrides["raft_layers"] = "0"
    # "skirt" or "" → leave preset defaults untouched.

    temp_model = None
    temp_gcode = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(t["file_data"])
            temp_model = f.name
        temp_gcode = temp_model + ".gcode"

        # fdm_creality_common (and several other bundled machine bases) enable
        # relative extrusion but rely on the GUI to inject `G92 E0` each layer;
        # the raw CLI does not, and refuses to slice. Default to absolute
        # extrusion unless the user overrides it.
        overrides.setdefault("use_relative_e_distances", 0)

        result = orca_tool.forward(
            model_path=temp_model,
            machine=machine,
            process=process,
            filament=filament,
            output_path=temp_gcode,
            overrides=overrides or None,
        )
        result_data = _tool_result_to_dict(result)
        if result_data is None:
            console.print(Text(f"Unexpected tool output: {str(result)[:200]}", style="bold red"))
            return
        _render_slice_result(
            t,
            thing_id,
            result_data,
            f"Sliced {t['file_name']} (OrcaSlicer)",
            temp_gcode,
        )
    except Exception as e:
        console.print(Text(f"Slicing failed: {e}", style="bold red"))
    finally:
        for p in (temp_model, temp_gcode):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
