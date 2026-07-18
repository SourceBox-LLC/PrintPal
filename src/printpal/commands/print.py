"""Print commands: /print and all /print sub-commands."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..ui import console, ACCENT, prompt_yes_no, format_size, format_duration, make_bar
from .. import db
from .helpers import call_tool, parse_gcode_temps, preheat


def cmd_print(args: list[str], tools: list) -> None:
    if not args or not args[0].isdigit():
        console.print(Text("Usage: /print <id> [--no-preheat]", style="dim"))
        return

    thing_id = int(args[0])
    no_preheat = "--no-preheat" in args

    t = db.get_thing(thing_id)
    if t is None:
        console.print(Text(f"No thing with ID {thing_id}.", style="bold red"))
        return
    if t["file_type"] != "gcode":
        console.print(
            Text(
                f"Thing #{thing_id} is a model. Slice it first: /slice {thing_id}",
                style="dim",
            )
        )
        return
    if t["file_data"] is None:
        console.print(Text(f"Thing #{thing_id} has no file data.", style="bold red"))
        return

    console.print(Text("Checking printer status...", style="dim"))
    status = call_tool(tools, "octoprint_get_status", response_format="json")
    if status is None:
        console.print(
            Text(
                "Could not read printer status. Is OctoPrint configured and running?",
                style="bold red",
            )
        )
        return

    ready = status.get("ready", False)
    conn_state = status.get("connection", {}).get("state", "unknown")

    if (
        "Offline" in str(conn_state)
        or "Closed" in str(conn_state)
        or conn_state == "unknown"
    ):
        if prompt_yes_no("Printer is not connected. Connect now? [y/N] "):
            result = call_tool(
                tools,
                "octoprint_connect",
                action="connect",
                confirm=True,
                response_format="json",
            )
            if result is None:
                console.print(
                    Text("Failed to connect to the printer.", style="bold red")
                )
                return
            time.sleep(2)
            status = call_tool(tools, "octoprint_get_status", response_format="json")
            ready = status.get("ready", False) if status else False

    if not ready:
        queue = db.get_queue()
        queue_msg = f" ({len(queue)} item(s) in queue)" if queue else ""
        if prompt_yes_no(
            f"Printer is busy or not ready{queue_msg}. Add to print queue? [y/N] "
        ):
            pos = db.add_to_queue(thing_id)
            console.print(
                Text(f"Added to queue (position {pos}).", style=f"bold {ACCENT}")
            )
        return

    if not no_preheat:
        tool_temp, bed_temp = parse_gcode_temps(t["file_data"])
        preheat(tools, tool_temp, bed_temp)

    console.print(
        Text(f"Uploading {t['file_name']} to OctoPrint...", style=f"bold {ACCENT}")
    )
    temp_gcode = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".gcode", delete=False) as f:
            f.write(t["file_data"])
            temp_gcode = f.name

        upload = call_tool(
            tools,
            "octoprint_upload_file",
            gcode_path=temp_gcode,
            response_format="json",
        )
        if upload is None:
            console.print(Text("Upload failed.", style="bold red"))
            return

        server_path = upload.get("server_path", t["file_name"])
        console.print(Text(f"  Uploaded to server: {server_path}", style="dim"))

        lines = [
            Text(
                f"File:        {t['file_name']} ({format_size(t['file_size'])})",
                style=f"bold {ACCENT}",
            ),
            Text(f"Server path: {server_path}"),
        ]
        if t["sliced_from"]:
            lines.append(Text(f"Sliced from: Thing #{t['sliced_from']}"))

        console.print(
            Panel(
                Text("\n").join(lines),
                title=Text("Print Details", style="bold"),
                border_style=ACCENT,
            )
        )

        if not prompt_yes_no("Start printing? [y/N] "):
            console.print(
                Text(
                    "Upload kept on server. Use /print files to start later.",
                    style="dim",
                )
            )
            return

        result = call_tool(
            tools,
            "octoprint_start_print",
            path=server_path,
            confirm=True,
            response_format="json",
        )
        if result is None:
            console.print(Text("Failed to start print.", style="bold red"))
            return

        db.update_thing_status(thing_id, "printing")
        console.print(
            Text("Print started! Use /print status to monitor.", style=f"bold {ACCENT}")
        )

        job = call_tool(tools, "octoprint_get_job", response_format="json")
        if job:
            console.print(Text(f"  State: {job.get('state', '?')}", style="dim"))
            console.print(Text(f"  File: {job.get('file', '?')}", style="dim"))

    except Exception as e:
        console.print(Text(f"Print failed: {e}", style="bold red"))
    finally:
        if temp_gcode:
            try:
                Path(temp_gcode).unlink(missing_ok=True)
            except OSError:
                pass


def _build_status_panel(tools: list) -> Panel:
    """Build the status panel for /print status live display."""
    status = call_tool(tools, "octoprint_get_status", response_format="json")
    if status is None:
        return Panel(
            Text(
                "Could not read printer status. Is OctoPrint configured and running?",
                style="bold red",
            ),
            title=Text("Printer Status", style="bold"),
            border_style=ACCENT,
        )

    lines = []
    server = status.get("server", {})
    if server.get("version"):
        lines.append(
            Text(
                f"OctoPrint:  {server.get('version', '?')} (API {server.get('api', '?')})"
            )
        )
    conn = status.get("connection", {})
    lines.append(Text(f"Connection: {conn.get('state', 'unknown') or 'unknown'}"))
    lines.append(
        Text(f"State:      {status.get('printer_state', 'unknown') or 'unknown'}")
    )
    lines.append(Text(f"Ready:      {'yes' if status.get('ready') else 'no'}"))

    temps = status.get("temperatures", {})
    if temps:
        lines.append(Text(""))
        lines.append(Text("Temperatures", style="bold"))
        for name in sorted(temps.keys()):
            t = temps[name]
            actual = t.get("actual", 0) or 0
            target = t.get("target", 0) or 0
            label = "Bed" if name == "bed" else name
            if target and target > 0:
                bar = make_bar(actual, target, 10)
                reached = " \u2713" if abs(actual - target) <= 2 else ""
                lines.append(
                    Text(
                        f"  {label:6s} {actual:.0f}\u00b0C \u2192 {target}\u00b0C  {bar}{reached}"
                    )
                )
            else:
                lines.append(Text(f"  {label:6s} {actual:.0f}\u00b0C"))

    job = call_tool(tools, "octoprint_get_job", response_format="json")
    if job and job.get("state") and job["state"] != "Offline":
        lines.append(Text(""))
        lines.append(Text("Current Job", style="bold"))
        lines.append(Text(f"  File:      {job.get('file', 'none') or 'none'}"))
        pct = job.get("completion_percent")
        if pct is not None:
            bar = make_bar(pct, 100, 16)
            lines.append(Text(f"  Progress:  {pct}%  {bar}"))
        elapsed = job.get("print_time_s")
        if elapsed:
            lines.append(Text(f"  Elapsed:   {format_duration(elapsed)}"))
        left = job.get("print_time_left_s")
        if left:
            lines.append(Text(f"  Remaining: {format_duration(left)} (est.)"))

    queue = db.get_queue()
    if queue:
        lines.append(Text(""))
        lines.append(Text(f"Print Queue: {len(queue)} item(s)", style="bold"))
        for q in queue[:3]:
            lines.append(
                Text(f"  #{q['position']}: Thing #{q['thing_id']} ({q['name']})")
            )

    lines.append(Text(""))
    lines.append(Text("Press Ctrl+C to stop monitoring.", style="dim"))

    return Panel(
        Text("\n").join(lines),
        title=Text("Printer Status", style="bold"),
        border_style=ACCENT,
    )


def cmd_print_status(tools: list) -> None:
    status = call_tool(tools, "octoprint_get_status", response_format="json")
    if status is None:
        console.print(
            Panel(
                Text(
                    "Could not read printer status. Is OctoPrint configured and running?\n\n"
                    "Set OCTOPRINT_URL and OCTOPRINT_API_KEY in your .env file.",
                    style="bold red",
                ),
                title=Text("Printer Status", style="bold"),
                border_style=ACCENT,
            )
        )
        return

    try:
        with Live(console=console, refresh_per_second=1) as live:
            _check_job_completion(tools)
            while True:
                panel = _build_status_panel(tools)
                live.update(panel)
                time.sleep(3)
    except KeyboardInterrupt:
        pass


def _check_job_completion(tools: list) -> None:
    """Check if a printing job has finished; update status if so."""
    job = call_tool(tools, "octoprint_get_job", response_format="json")
    if not job:
        return
    state = job.get("state", "")
    if state == "Operational":
        things = db.list_things()
        for t in things:
            if t["status"] == "printing":
                db.update_thing_status(t["id"], "printed")
                console.print(
                    Text(
                        f"  Job complete: Thing #{t['id']} ({t['name']}) marked as printed.",
                        style="green",
                    )
                )
        queue = db.get_queue()
        if queue:
            next_item = queue[0]
            console.print(
                Text(
                    f"  Next in queue: Thing #{next_item['thing_id']} ({next_item['name']}). "
                    f"Use /print {next_item['thing_id']} to start it.",
                    style=f"bold {ACCENT}",
                )
            )


def cmd_print_pause(tools: list) -> None:
    if prompt_yes_no("Pause the print? [y/N] "):
        result = call_tool(
            tools,
            "octoprint_control_job",
            action="pause",
            confirm=True,
            response_format="json",
        )
        console.print(
            Text("Print paused.", style=f"bold {ACCENT}")
            if result
            else Text("Failed to pause.", style="bold red")
        )


def cmd_print_resume(tools: list) -> None:
    if prompt_yes_no("Resume the print? [y/N] "):
        result = call_tool(
            tools,
            "octoprint_control_job",
            action="resume",
            confirm=True,
            response_format="json",
        )
        console.print(
            Text("Print resumed.", style=f"bold {ACCENT}")
            if result
            else Text("Failed to resume.", style="bold red")
        )


def cmd_print_cancel(tools: list) -> None:
    if prompt_yes_no("Cancel the print? The partial object will be wasted. [y/N] "):
        result = call_tool(
            tools,
            "octoprint_control_job",
            action="cancel",
            confirm=True,
            response_format="json",
        )
        if result:
            for t in db.list_things():
                if t["status"] == "printing":
                    db.update_thing_status(t["id"], "sliced")
            console.print(
                Text(
                    "Print cancelled. G-code kept for reprinting.",
                    style=f"bold {ACCENT}",
                )
            )
        else:
            console.print(Text("Failed to cancel.", style="bold red"))


def cmd_print_connect(tools: list) -> None:
    if prompt_yes_no("Connect to the printer? [y/N] "):
        result = call_tool(
            tools,
            "octoprint_connect",
            action="connect",
            confirm=True,
            response_format="json",
        )
        console.print(
            Text("Connected.", style=f"bold {ACCENT}")
            if result
            else Text("Failed to connect.", style="bold red")
        )


def cmd_print_disconnect(tools: list) -> None:
    if prompt_yes_no("Disconnect from the printer? [y/N] "):
        result = call_tool(
            tools,
            "octoprint_connect",
            action="disconnect",
            confirm=True,
            response_format="json",
        )
        console.print(
            Text("Disconnected.", style=f"bold {ACCENT}")
            if result
            else Text("Failed to disconnect.", style="bold red")
        )


def cmd_print_files(tools: list) -> None:
    result = call_tool(tools, "octoprint_list_files", response_format="json")
    if result is None:
        console.print(
            Text("Could not list files. Is OctoPrint configured?", style="bold red")
        )
        return
    files = result.get("files", [])
    if not files:
        console.print(Text("No G-code files on the server.", style="dim"))
        return
    table = Table(
        show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT
    )
    table.add_column("Path", style=f"bold {ACCENT}", min_width=20)
    table.add_column("Size", justify="right", width=10)
    table.add_column("Est. Time", width=15)
    for f in files:
        est = (
            format_duration(f.get("estimated_print_time_s"))
            if f.get("estimated_print_time_s")
            else "?"
        )
        table.add_row(f.get("path", "?"), format_size(f.get("size_bytes")), est)
    console.print(table)


def cmd_print_queue(args: list[str]) -> None:
    if args and args[0] == "remove":
        if len(args) < 2:
            console.print(Text("Usage: /print queue remove <position>", style="dim"))
            return
        try:
            pos = int(args[1])
        except ValueError:
            console.print(Text("Position must be a number.", style="bold red"))
            return
        if db.remove_from_queue(pos):
            console.print(
                Text(f"Removed position {pos} from queue.", style=f"bold {ACCENT}")
            )
        else:
            console.print(Text(f"No queue item at position {pos}.", style="bold red"))
        return

    if args and args[0] == "clear":
        count = db.clear_queue()
        console.print(
            Text(f"Cleared {count} item(s) from queue.", style=f"bold {ACCENT}")
        )
        return

    queue = db.get_queue()
    if not queue:
        console.print(Text("Print queue is empty.", style="dim"))
        return
    table = Table(
        show_header=True, header_style="bold", box=box.HORIZONTALS, border_style=ACCENT
    )
    table.add_column("Pos", style="dim", width=5)
    table.add_column("Thing ID", width=10)
    table.add_column("Name", style=f"bold {ACCENT}", min_width=20)
    table.add_column("Added", style="dim")
    for q in queue:
        table.add_row(str(q["position"]), str(q["thing_id"]), q["name"], q["added_at"])
    console.print(table)
