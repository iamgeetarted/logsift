"""Command-line interface for logsift."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from .analyzer import stream_analysis
from .config import load_config
from .display import (
    console,
    make_stats_panel,
    make_summary_table,
    make_timeline_panel,
    print_ai_header,
    print_follow_line,
)
from .exporter import to_csv, to_markdown
from .fetcher import load_sources
from .grouper import group_lines
from .parser import Level, parse_lines, parse_timestamp_dt


def _build_parser(cfg_defaults) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="logsift",
        description="Async log analyzer with AI-powered insights.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  logsift app.log                      # analyze a local log file
  logsift *.log                        # analyze multiple files
  logsift --url https://host/build.log # fetch and analyze remote log
  cat app.log | logsift                # read from stdin
  logsift app.log --no-ai              # skip AI analysis
  logsift app.log --level error        # show only ERROR+ lines
  logsift app.log --format json        # structured JSON output
  logsift app.log --format markdown    # Markdown report (great for GitHub Issues)
  logsift app.log --format csv         # CSV for spreadsheets / pandas
  logsift app.log --watch 10           # re-analyze every 10 seconds
  logsift app.log --threshold 0.6      # tighter similarity grouping
  logsift app.log --grep 'database'    # only lines matching pattern
  logsift app.log --grep 'ERROR' --grep 'auth'  # AND-match multiple patterns
  logsift app.log --format json -o report.json  # write output to file
  logsift app.log --timeline           # show time-bucketed event histogram
  logsift app.log --since "2024-01-15 08:00"   # only lines after this time
  logsift app.log --until "2024-01-15 09:30"   # only lines before this time
  logsift app.log --follow             # live colorized tail (like tail -f + Rich)
  logsift app.log --verbose            # show timing for each analysis stage

config file (~/.logsift.toml):
  [defaults]
  threshold = 0.5
  format = "table"
  no_ai = false
  watch = 30
""",
    )
    p.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Log files to analyze",
    )
    p.add_argument(
        "--url",
        action="append",
        default=[],
        metavar="URL",
        help="Fetch log from URL (repeatable)",
    )
    p.add_argument(
        "--no-ai",
        action="store_true",
        default=cfg_defaults.no_ai,
        help="Skip AI analysis",
    )
    p.add_argument(
        "--level",
        choices=["debug", "info", "warning", "error", "critical"],
        default=cfg_defaults.level,
        metavar="LEVEL",
        help="Filter: only show lines at or above this level",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=cfg_defaults.threshold,
        metavar="FLOAT",
        help="Cosine similarity threshold for grouping (0-1, default: 0.45)",
    )
    p.add_argument(
        "--top",
        type=int,
        default=cfg_defaults.top,
        metavar="N",
        help="Show top N groups (default: 20)",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["table", "json", "markdown", "csv"],
        default=cfg_defaults.format,
        help="Output format (default: table)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=cfg_defaults.timeout,
        metavar="SECONDS",
        help="HTTP timeout for remote logs (default: 30s)",
    )
    p.add_argument(
        "--watch",
        type=int,
        default=cfg_defaults.watch,
        metavar="SECS",
        help="Re-analyze every SECS seconds (watch mode; local files only)",
    )
    p.add_argument(
        "--grep",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Only analyze lines matching regex PATTERN (repeatable — all must match)",
    )
    p.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        default=None,
        help="Write output to FILE instead of stdout (applies to json/csv/markdown formats)",
    )
    p.add_argument(
        "--timeline",
        action="store_true",
        default=False,
        help="Show a time-bucketed histogram of log events (requires timestamps in logs)",
    )
    p.add_argument(
        "--since",
        metavar="DATETIME",
        default=None,
        help='Only include lines at or after this time (e.g. "2024-01-15 08:00")',
    )
    p.add_argument(
        "--until",
        metavar="DATETIME",
        default=None,
        help='Only include lines at or before this time (e.g. "2024-01-15 09:30")',
    )
    p.add_argument(
        "--follow",
        action="store_true",
        default=False,
        help="Live colorized tail — stream new lines as they are appended (like tail -f with Rich)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Show structured timing for each analysis stage (load, parse, group, AI)",
    )
    p.add_argument(
        "--alert-threshold",
        type=int,
        default=None,
        metavar="N",
        help="Fire --webhook when error+critical line count exceeds N",
    )
    p.add_argument(
        "--webhook",
        default=None,
        metavar="URL",
        help="Webhook URL to POST an alert payload when --alert-threshold is triggered",
    )
    p.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Randomly sample N lines before analysis (useful for very large log files)",
    )
    p.add_argument(
        "--dedup",
        action="store_true",
        default=False,
        help="Merge consecutive near-identical log lines before analysis (removes repetitive noise)",
    )
    p.add_argument("--version", action="version", version=f"logsift {__version__}")
    return p


_LEVEL_ORDER = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "error": 3,
    "critical": 4,
}

_LEVEL_MAP = {
    "debug": Level.DEBUG,
    "info": Level.INFO,
    "warning": Level.WARNING,
    "error": Level.ERROR,
    "critical": Level.CRITICAL,
}


def _filter_level(lines, min_level_name: str | None):
    if not min_level_name:
        return lines
    min_ord = _LEVEL_ORDER[min_level_name]
    level_ords = {v: _LEVEL_ORDER.get(v.value.lower(), 99) for v in Level}
    return [l for l in lines if level_ords.get(l.level, 99) >= min_ord]


def _parse_dt_arg(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}  (use 'YYYY-MM-DD HH:MM')")


def _filter_timerange(lines, since: datetime | None, until: datetime | None):
    if since is None and until is None:
        return lines
    result = []
    for line in lines:
        if not line.timestamp:
            result.append(line)
            continue
        dt = parse_timestamp_dt(line.timestamp)
        if dt is None:
            result.append(line)
            continue
        if since and dt < since:
            continue
        if until and dt > until:
            continue
        result.append(line)
    return result


async def _follow_file(path: Path, args: argparse.Namespace) -> int:
    """Live colorized tail: stream new lines from a file as they are appended."""
    if not path.exists():
        console.print(f"[red]File not found:[/red] {path}", highlight=False)
        return 2

    grep_res = [re.compile(p) for p in (args.grep or [])]
    min_level_name = args.level
    min_ord = _LEVEL_ORDER.get(min_level_name, 0) if min_level_name else 0
    level_ords = {v: _LEVEL_ORDER.get(v.value.lower(), 99) for v in Level}

    console.print(
        f"[bold cyan]logsift --follow[/bold cyan]  [dim]{path}[/dim]  "
        f"[dim](Ctrl-C to stop)[/dim]"
    )
    console.rule(style="dim")

    with path.open(errors="replace") as fh:
        fh.seek(0, 2)  # seek to end
        while True:
            line = fh.readline()
            if not line:
                await asyncio.sleep(0.2)
                continue
            raw = line.rstrip("\n")
            if not raw.strip():
                continue
            if grep_res and not all(r.search(raw) for r in grep_res):
                continue
            parsed_lines = parse_lines([raw])
            if not parsed_lines:
                continue
            pl = parsed_lines[0]
            if min_level_name and level_ords.get(pl.level, 99) < min_ord:
                continue
            print_follow_line(pl)


async def _analyze_once(args: argparse.Namespace, iteration: int = 0) -> tuple[int, list[dict]]:
    """Run a single analysis pass. Returns (exit_code, json_results)."""
    paths = [Path(f) for f in args.files]
    for p in paths:
        if not p.exists():
            console.print(f"[red]File not found:[/red] {p}", highlight=False)
            return 2, []

    from_stdin = not sys.stdin.isatty() and not paths and not args.url

    since_dt: datetime | None = None
    until_dt: datetime | None = None
    if getattr(args, "since", None):
        try:
            since_dt = _parse_dt_arg(args.since)
        except ValueError as e:
            console.print(f"[red]--since:[/red] {e}")
            return 2, []
    if getattr(args, "until", None):
        try:
            until_dt = _parse_dt_arg(args.until)
        except ValueError as e:
            console.print(f"[red]--until:[/red] {e}")
            return 2, []

    verbose = getattr(args, "verbose", False)

    t_load = time.monotonic()
    try:
        sources = await load_sources(paths, args.url, from_stdin, timeout=args.timeout)
    except Exception as exc:
        console.print(f"[red]Failed to load source:[/red] {exc}")
        return 1, []
    if verbose:
        console.print(f"[dim]  load   {time.monotonic()-t_load:.3f}s — {len(sources)} source(s)[/dim]")

    if not sources:
        console.print("[yellow]No input provided. Pass a file, --url, or pipe via stdin.[/yellow]")
        return 1, []

    all_results: list[dict] = []

    grep_res = [re.compile(p) for p in (args.grep or [])]

    for source_name, raw_lines in sources:
        # Apply --grep before parsing (cheap string filter)
        if grep_res:
            raw_lines = [l for l in raw_lines if all(r.search(l) for r in grep_res)]

        sample_n = getattr(args, "sample", None)
        if sample_n is not None and len(raw_lines) > sample_n:
            import random
            orig_count = len(raw_lines)
            raw_lines = random.sample(raw_lines, sample_n)
            if verbose:
                console.print(f"[dim]  sample {sample_n}/{orig_count} lines[/dim]")

        if getattr(args, "dedup", False):
            from .deduplicator import dedup_lines
            orig_count = len(raw_lines)
            raw_lines = dedup_lines(raw_lines)
            if verbose:
                console.print(f"[dim]  dedup  {orig_count} → {len(raw_lines)} lines[/dim]")

        t_parse = time.monotonic()
        lines = parse_lines(raw_lines)
        if verbose:
            console.print(f"[dim]  parse  {time.monotonic()-t_parse:.3f}s — {len(lines)} lines[/dim]")

        lines = _filter_level(lines, args.level)
        lines = _filter_timerange(lines, since_dt, until_dt)
        if verbose and (since_dt or until_dt):
            console.print(f"[dim]  filter {len(lines)} lines in time window[/dim]")

        if not lines:
            console.print(f"[dim]{source_name}: no lines matched.[/dim]")
            continue

        t_group = time.monotonic()
        groups = group_lines(lines, threshold=args.threshold)
        if verbose:
            console.print(f"[dim]  group  {time.monotonic()-t_group:.3f}s — {len(groups)} groups (threshold={args.threshold})[/dim]")

        alert_threshold = getattr(args, "alert_threshold", None)
        webhook_url = getattr(args, "webhook", None)
        if alert_threshold is not None and webhook_url:
            from .alerting import should_alert, fire_webhook
            from .parser import Level as _Level
            if should_alert(lines, alert_threshold):
                fired = fire_webhook(webhook_url, source_name, lines, groups, alert_threshold)
                err_n = sum(1 for l in lines if l.level in (_Level.ERROR, _Level.CRITICAL))
                status = "[green]fired[/green]" if fired else "[red]failed[/red]"
                console.print(f"[bold yellow]⚡ Alert:[/bold yellow] {err_n} errors > threshold {alert_threshold} → webhook {status}")

        if args.format == "json":
            for g in groups:
                all_results.append({
                    "source": source_name,
                    "group_label": g.label,
                    "count": g.count,
                    "sample": g.lines[0].raw if g.lines else "",
                    "lines": [l.lineno for l in g.lines],
                })
            continue

        if args.format == "csv":
            all_results.append({"_csv": to_csv(groups, source_name)})
            continue

        if args.format == "markdown":
            ai_text = ""
            if not args.no_ai:
                ai_text = "".join(stream_analysis(groups, source_name))
            md = to_markdown(lines, groups, source_name, top=args.top, ai_text=ai_text)
            all_results.append({"_md": md})
            continue

        # Rich table display
        if args.watch and iteration > 0:
            console.clear()

        console.print()
        console.print(make_stats_panel(lines, groups))
        console.print(make_summary_table(groups[:args.top], source_name))

        if args.timeline:
            tl = make_timeline_panel(lines)
            if tl is not None:
                console.print()
                console.print(tl)

        if not args.no_ai:
            console.print()
            print_ai_header()
            t_ai = time.monotonic()
            for chunk in stream_analysis(groups, source_name):
                console.print(chunk, end="")
            console.print("\n")
            if verbose:
                console.print(f"[dim]  ai     {time.monotonic()-t_ai:.3f}s[/dim]")

    return 0, all_results


async def _run(args: argparse.Namespace) -> int:
    if getattr(args, "follow", False):
        paths = [Path(f) for f in args.files]
        if not paths:
            console.print("[red]--follow requires a local file path.[/red]")
            return 2
        if len(paths) > 1:
            console.print("[red]--follow supports exactly one file at a time.[/red]")
            return 2
        return await _follow_file(paths[0], args)

    if args.watch and args.format == "table":
        iteration = 0
        while True:
            t0 = time.monotonic()
            code, _ = await _analyze_once(args, iteration)
            elapsed = time.monotonic() - t0
            wait = max(0.0, args.watch - elapsed)
            console.print(
                f"[dim]  ↻ watch mode — refreshing in {args.watch}s "
                f"(Ctrl-C to stop)[/dim]"
            )
            try:
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                break
            iteration += 1
        return 0

    code, all_results = await _analyze_once(args)

    if args.format == "json":
        text = json.dumps(all_results, indent=2)
        _output(text, args.output)
    elif args.format == "csv":
        text = "".join(r.get("_csv", "") for r in all_results)
        _output(text, args.output)
    elif args.format == "markdown":
        text = "".join(r.get("_md", "") for r in all_results)
        _output(text, args.output)

    return code


def _output(text: str, path: str | None) -> None:
    if path:
        Path(path).write_text(text, encoding="utf-8")
        console.print(f"[dim]Output written to {path}[/dim]", highlight=False)
    else:
        print(text, end="")


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    parser = _build_parser(cfg)
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0


def entry_point() -> None:
    sys.exit(main())
