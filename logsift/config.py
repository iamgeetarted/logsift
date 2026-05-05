"""Load persistent defaults from ~/.logsift.toml (optional)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_PATH = Path.home() / ".logsift.toml"


@dataclass
class LogsiftConfig:
    threshold: float = 0.45
    top: int = 20
    format: str = "table"
    level: str | None = None
    no_ai: bool = False
    timeout: float = 30.0
    watch: int | None = None


def load_config() -> LogsiftConfig:
    """Read ~/.logsift.toml and return a LogsiftConfig with overrides applied."""
    cfg = LogsiftConfig()
    if not _CONFIG_PATH.exists():
        return cfg

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return cfg

    try:
        raw = tomllib.loads(_CONFIG_PATH.read_text())
        defaults = raw.get("defaults", raw)
        if "threshold" in defaults:
            cfg.threshold = float(defaults["threshold"])
        if "top" in defaults:
            cfg.top = int(defaults["top"])
        if "format" in defaults:
            cfg.format = str(defaults["format"])
        if "level" in defaults:
            cfg.level = str(defaults["level"])
        if "no_ai" in defaults:
            cfg.no_ai = bool(defaults["no_ai"])
        if "timeout" in defaults:
            cfg.timeout = float(defaults["timeout"])
        if "watch" in defaults:
            cfg.watch = int(defaults["watch"])
    except Exception:
        pass

    return cfg
