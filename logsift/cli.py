"""Command-line interface for logsift."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from . import __version__
from .analyzer import stream_analysis
from .config import load_config
from .display import (
    console,
    make_stats_panel,
    make_summary_table,
    print_ai_header,
)
from .exporter import to_csv, to_markdown
from .fetcher import load_sources
from .grouper import group_lines
from .parser import Level, parse_lines


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


async def _analyze_once(args: argparse.Namespace, iteration: int = 0) -> tuple[int, list[dict]]:
    """Run a single analysis pass. Returns (exit_code, json_results)."""
    paths = [Path(f) for f in args.files]
    for p in paths:
        if not p.exists():
            console.print(f"[red]File not found:[/red] {p}", highlight=False)
            return 2, []

    from_stdin = not sys.stdin.isatty() and not paths and not args.url

    try:
        sources = await load_sources(paths, args.url, from_stdin, timeout=args.timeout)
    except Exception as exc:
        console.print(f"[red]Failed to load source:[/red] {exc}")
        return 1, []

    if not sources:
        console.print("[yellow]No input provided. Pass a file, --url, or pipe via stdin.[/yellow]")
        return 1, []

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

        if not args.no_ai:
            console.print()
            print_ai_header()
            for chunk in stream_analysis(groups, source_name):
                console.print(chunk, end="")
            console.print("\n")

    return 0, all_results


async def _run(args: argparse.Namespace) -> int:
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
        print(json.dumps(all_results, indent=2))
    elif args.format == "csv":
        for r in all_results:
            print(r.get("_csv", ""), end="")
    elif args.format == "markdown":
        for r in all_results:
            print(r.get("_md", ""), end="")

    return code


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
