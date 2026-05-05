"""Export log analysis results to Markdown or CSV."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .grouper import Group
from .parser import Level, LogLine


def to_markdown(
    lines: list[LogLine],
    groups: list[Group],
    source_name: str,
    top: int = 20,
    ai_text: str = "",
) -> str:
    """Render analysis results as a Markdown report string."""
    from collections import Counter

    level_counts: Counter[Level] = Counter(l.level for l in lines)
    total = len(lines)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines_md: list[str] = [
        f"# logsift report: `{source_name}`",
        f"",
        f"_Generated {now}_",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total lines | {total} |",
    ]
    for level in (Level.CRITICAL, Level.ERROR, Level.WARNING, Level.INFO, Level.DEBUG):
        n = level_counts.get(level, 0)
        if n:
            lines_md.append(f"| {level.value} | {n} |")
    lines_md += [
        f"| Groups | {len(groups)} |",
        "",
        "## Top Patterns",
        "",
        "| # | Count | Level | Sample |",
        "|---|------:|-------|--------|",
    ]

    for i, g in enumerate(groups[:top], 1):
        dominant = _dominant(g)
        sample = g.lines[0].raw[:120].replace("|", "\\|").replace("\n", " ")
        lines_md.append(f"| {i} | {g.count} | {dominant.value} | `{sample}` |")

    if ai_text:
        lines_md += [
            "",
            "## AI Analysis",
            "",
            ai_text.strip(),
        ]

    return "\n".join(lines_md) + "\n"


def to_csv(groups: list[Group], source_name: str) -> str:
    """Render groups as a CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["source", "count", "level", "sample", "first_ts"])
    for g in groups:
        dominant = _dominant(g)
        sample = g.lines[0].raw[:200].replace("\n", " ") if g.lines else ""
        ts = g.lines[0].timestamp if g.lines else ""
        writer.writerow([source_name, g.count, dominant.value, sample, ts])
    return buf.getvalue()


def _dominant(group: Group) -> Level:
    from collections import Counter
    counts: Counter[Level] = Counter(l.level for l in group.lines)
    for lvl in (Level.CRITICAL, Level.ERROR, Level.WARNING, Level.INFO, Level.DEBUG, Level.UNKNOWN):
        if counts.get(lvl, 0) > 0:
            return lvl
    return Level.UNKNOWN
