"""Stream AI analysis of log patterns using the Anthropic API."""

from __future__ import annotations

import os
from typing import Iterator

from .grouper import Group
from .parser import Level


def _build_prompt(groups: list[Group], source_name: str) -> str:
    total = sum(g.count for g in groups)
    error_groups = [g for g in groups if any(l.is_error_like for l in g.lines)]
    warn_groups = [g for g in groups if any(l.level == Level.WARNING for l in g.lines)]

    lines = [
        f"Analyze these log patterns from `{source_name}` ({total} total lines).",
        "",
        "TOP ERROR/WARNING PATTERNS:",
    ]

    shown = 0
    for g in (error_groups + warn_groups)[:8]:
        sample = g.lines[0].raw[:200]
        lines.append(f"- [{g.count}x] {sample}")
        shown += 1

    if shown == 0:
        for g in groups[:5]:
            sample = g.lines[0].raw[:200]
            lines.append(f"- [{g.count}x] {sample}")

    lines += [
        "",
        "Provide a concise 3-5 sentence analysis:",
        "1. What is the main issue or activity shown?",
        "2. What is likely causing the errors/warnings?",
        "3. What action should be taken?",
        "",
        "Be specific, technical, and actionable. No fluff.",
    ]
    return '\n'.join(lines)


def stream_analysis(groups: list[Group], source_name: str) -> Iterator[str]:
    """Stream an AI analysis of the log groups. Yields text chunks as they arrive."""
    try:
        import anthropic
    except ImportError:
        yield "\n[!] Install anthropic to enable AI analysis: pip install anthropic\n"
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield "\n[!] Set ANTHROPIC_API_KEY environment variable to enable AI analysis.\n"
        return

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(groups, source_name)

    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
