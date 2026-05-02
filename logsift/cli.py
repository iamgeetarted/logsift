"""Command-line interface for logsift."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .analyzer import stream_analysis
from .display import (
    console,
    make_stats_panel,
    make_summary_table,
    print_ai_header,
)
from .fetcher import load_sources
from .grouper import group_lines
from .parser import Level, parse_lines


def _build_parser() -> argparse.ArgumentParser:
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
  logsift app.log --threshold 0.6      # tighter similarity grouping
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
        help="Skip AI analysis",
    )
    p.add_argument(
        "--level",
        choices=["debug", "info", "warning", "error", "critical"],
        default=None,
        metavar="LEVEL",
        help="Filter: only show lines at or above this level",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.45,
        metavar="FLOAT",
        help="Cosine similarity threshold for grouping (0-1, default: 0.45)",
    )
    p.add_argument(
        "--top",
        type=int,
        default=20,
        metavar="N",
        help="Show top N groups (default: 20)",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="HTTP timeout for remote logs (default: 30s)",
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


async def _run(args: argparse.Namespace) -> int:
    paths = [Path(f) for f in args.files]
    for p in paths:
        if not p.exists():
            console.print(f"[red]File not found:[/red] {p}", highlight=False)
            return 2

    from_stdin = not sys.stdin.isatty() and not paths and not args.url

    try:
        sources = await load_sources(paths, args.url, from_stdin, timeout=args.timeout)
    except Exception as exc:
        console.print(f"[red]Failed to load source:[/red] {exc}")
        return 1

    if not sources:
        console.print("[yellow]No input provided. Pass a file, --url, or pipe via stdin.[/yellow]")
        return 1

    all_results: list[dict] = []

    for source_name, raw_lines in sources:
        lines = parse_lines(raw_lines)
        lines = _filter_level(lines, args.level)

        if not lines:
            console.print(f"[dim]{source_name}: no lines matched.[/dim]")
            continue

        groups = group_lines(lines, threshold=args.threshold)

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

        # Rich table display
        console.print()
        console.print(make_stats_panel(lines, groups))
        console.print(make_summary_table(groups[:args.top], source_name))

        if not args.no_ai:
            console.print()
            print_ai_header()
            for chunk in stream_analysis(groups, source_name):
                console.print(chunk, end="")
            console.print("\n")

    if args.format == "json":
        print(json.dumps(all_results, indent=2))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


def entry_point() -> None:
    sys.exit(main())
