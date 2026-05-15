"""Deduplicate consecutive repeated log lines before analysis."""
from __future__ import annotations
import re


_NORM_RE = re.compile(r'\d+')


def _normalize(text: str) -> str:
    """Strip numbers for comparison so 'retry 1' and 'retry 2' deduplicate."""
    return _NORM_RE.sub('N', text.lower()).strip()


def dedup_lines(raw_lines: list[str]) -> list[str]:
    """Merge consecutive near-identical lines into one with a count prefix.

    Lines that normalize to the same pattern are collapsed.
    Returns a new list — original is not modified.
    """
    if not raw_lines:
        return []

    result: list[str] = []
    current_norm = _normalize(raw_lines[0])
    current_line = raw_lines[0]
    count = 1

    for line in raw_lines[1:]:
        norm = _normalize(line)
        if norm == current_norm:
            count += 1
        else:
            if count > 1:
                result.append(f"[{count}x] {current_line}")
            else:
                result.append(current_line)
            current_norm = norm
            current_line = line
            count = 1

    # flush last group
    if count > 1:
        result.append(f"[{count}x] {current_line}")
    else:
        result.append(current_line)

    return result
