"""Parse raw log lines into structured records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class Level(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


_LEVEL_PATTERNS: list[tuple[Level, re.Pattern[str]]] = [
    (Level.CRITICAL, re.compile(r'\b(CRITICAL|FATAL|EMERG|ALERT)\b', re.IGNORECASE)),
    (Level.ERROR,    re.compile(r'\b(ERROR|ERR|SEVERE|EXCEPTION|TRACEBACK)\b', re.IGNORECASE)),
    (Level.WARNING,  re.compile(r'\b(WARN(?:ING)?|CAUTION)\b', re.IGNORECASE)),
    (Level.INFO,     re.compile(r'\b(INFO|NOTICE|INFORMATION)\b', re.IGNORECASE)),
    (Level.DEBUG,    re.compile(r'\b(DEBUG|TRACE|VERBOSE)\b', re.IGNORECASE)),
]

_TS_RE = re.compile(
    r'(?:'
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?'
    r'|\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}'
    r'|\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}'
    r')'
)


@dataclass
class LogLine:
    lineno: int
    raw: str
    level: Level = Level.UNKNOWN
    timestamp: str = ""
    message: str = ""
    tokens: list[str] = field(default_factory=list, repr=False)

    @property
    def is_error_like(self) -> bool:
        return self.level in (Level.ERROR, Level.CRITICAL)

    @property
    def is_noise(self) -> bool:
        return self.level in (Level.DEBUG, Level.INFO) and not self.is_error_like


def _detect_level(text: str) -> Level:
    for level, pat in _LEVEL_PATTERNS:
        if pat.search(text):
            return level
    return Level.UNKNOWN


def _extract_timestamp(text: str) -> str:
    m = _TS_RE.search(text)
    return m.group(0) if m else ""


_NON_WORD = re.compile(r'[^\w]')
_DIGITS = re.compile(r'\b\d+\b')


def _tokenize(text: str) -> list[str]:
    """Extract meaningful tokens — strip digits and short tokens for grouping."""
    text = _DIGITS.sub('N', text)
    tokens = _NON_WORD.split(text.lower())
    return [t for t in tokens if len(t) > 2]


def parse_lines(raw_lines: Sequence[str]) -> list[LogLine]:
    """Parse a sequence of raw log strings into LogLine objects."""
    result: list[LogLine] = []
    for i, raw in enumerate(raw_lines, start=1):
        line = raw.rstrip('\n')
        if not line.strip():
            continue
        ts = _extract_timestamp(line)
        level = _detect_level(line)
        msg = line
        if ts:
            msg = line.replace(ts, '', 1).strip(' -|[]')
        result.append(LogLine(
            lineno=i,
            raw=line,
            level=level,
            timestamp=ts,
            message=msg,
            tokens=_tokenize(msg),
        ))
    return result
