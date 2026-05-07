"""Rich terminal display components for logsift."""

from __future__ import annotations

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.text import Text

from .grouper import Group
from .parser import Level, LogLine

console = Console(highlight=False)


_LEVEL_STYLE: dict[Level, str] = {
    Level.CRITICAL: "bold red",
    Level.ERROR: "red",
    Level.WARNING: "yellow",
    Level.INFO: "cyan",
    Level.DEBUG: "dim",
    Level.UNKNOWN: "",
}


def make_summary_table(groups: list[Group], source_name: str) -> Table:
    """Build the summary Rich Table showing grouped log patterns."""
    table = Table(
        title=f"[bold cyan]{source_name}[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Count", width=7, justify="right", style="bold")
    table.add_column("Level", width=9, justify="center")
    table.add_column("Pattern / Sample", ratio=3)
    table.add_column("First Seen", width=22, style="dim")

    for group in groups[:30]:
        dominant_level = _dominant_level(group)
        level_text = Text(dominant_level.value, style=_LEVEL_STYLE[dominant_level])
        sample = group.lines[0].raw[:120].replace('\n', ' ')
        ts = group.lines[0].timestamp or "—"
        count_style = "red" if dominant_level in (Level.ERROR, Level.CRITICAL) else (
            "yellow" if dominant_level == Level.WARNING else "green"
        )
        table.add_row(
            Text(str(group.count), style=count_style),
            level_text,
            sample,
            ts,
        )
    return table


def make_stats_panel(lines: list[LogLine], groups: list[Group]) -> Panel:
    """Build a small stats panel showing level distribution."""
    from collections import Counter
    level_counts: Counter[Level] = Counter(l.level for l in lines)
    total = len(lines)

    parts: list[str] = [f"[dim]Total lines:[/dim] [bold]{total}[/bold]   "]
    for level in (Level.CRITICAL, Level.ERROR, Level.WARNING, Level.INFO, Level.DEBUG):
        n = level_counts.get(level, 0)
        if n:
            style = _LEVEL_STYLE[level]
            parts.append(f"[{style}]{level.value}: {n}[/{style}]  " if style else f"{level.value}: {n}  ")

    parts.append(f"[dim]Groups: {len(groups)}[/dim]")
    return Panel(" ".join(parts), box=box.MINIMAL, style="dim")


def make_loading_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
        console=console,
    )


def print_ai_header() -> None:
    console.print(Panel("[bold cyan]AI Analysis[/bold cyan]", box=box.ROUNDED, style="cyan"))


def _dominant_level(group: Group) -> Level:
    from collections import Counter
    counts: Counter[Level] = Counter(l.level for l in group.lines)
    priority = [Level.CRITICAL, Level.ERROR, Level.WARNING, Level.INFO, Level.DEBUG, Level.UNKNOWN]
    for lvl in priority:
        if counts.get(lvl, 0) > 0:
            return lvl
    return Level.UNKNOWN


def make_timeline_panel(lines: list[LogLine]) -> Panel | None:
    """Build a time-bucketed histogram panel. Returns None if no timestamps found."""
    import re
    from collections import Counter, defaultdict
    from datetime import datetime

    _DT_PATTERNS = [
        (re.compile(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})'), "%Y-%m-%d %H:%M"),
        (re.compile(r'(\d{2}/\w{3}/\d{4}):(\d{2}):(\d{2})'), None),
        (re.compile(r'\w{3}\s+\d{1,2}\s+(\d{2}):(\d{2})'), None),
    ]

    # Try to parse hour-level buckets from timestamps
    buckets: Counter[str] = Counter()
    bucket_levels: dict[str, Counter] = defaultdict(Counter)

    for line in lines:
        if not line.timestamp:
            continue
        ts = line.timestamp
        # Try ISO-like format
        m = re.match(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})', ts)
        if m:
            key = f"{m.group(1)} {m.group(2)}:00"
            buckets[key] += 1
            bucket_levels[key][line.level] += 1
            continue
        # Try HH:MM
        m = re.match(r'(\d{2}):(\d{2})', ts)
        if m:
            key = f"{m.group(1)}:00"
            buckets[key] += 1
            bucket_levels[key][line.level] += 1

    if not buckets:
        return None

    # Build a mini bar chart
    sorted_keys = sorted(buckets.keys())
    max_count = max(buckets.values()) or 1
    bar_width = 28

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan", pad_edge=False)
    table.add_column("Time Bucket", style="cyan", width=20)
    table.add_column("Count", justify="right", width=6)
    table.add_column("Distribution", width=bar_width + 2)
    table.add_column("Levels", width=22)

    for key in sorted_keys:
        count = buckets[key]
        bar_len = max(1, int(count / max_count * bar_width))

        lvl_counts = bucket_levels[key]
        err_n = lvl_counts.get(Level.ERROR, 0) + lvl_counts.get(Level.CRITICAL, 0)
        warn_n = lvl_counts.get(Level.WARNING, 0)
        ok_n = count - err_n - warn_n

        bar_color = "red" if err_n > warn_n else ("yellow" if warn_n else "green")
        bar = Text("█" * bar_len, style=bar_color)

        lvl_parts: list[str] = []
        if err_n:
            lvl_parts.append(f"[red]E:{err_n}[/red]")
        if warn_n:
            lvl_parts.append(f"[yellow]W:{warn_n}[/yellow]")
        if ok_n:
            lvl_parts.append(f"[dim]I:{ok_n}[/dim]")

        table.add_row(key, str(count), bar, "  ".join(lvl_parts))

    return Panel(table, title="[bold]Event Timeline[/bold]", border_style="cyan", box=box.ROUNDED)
