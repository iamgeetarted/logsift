"""Webhook alerting: POST a JSON payload when error count exceeds a threshold."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .grouper import Group
    from .parser import LogLine

def should_alert(lines: list["LogLine"], threshold: int) -> bool:
    """Return True if error+critical line count exceeds threshold."""
    from .parser import Level
    error_count = sum(1 for l in lines if l.level in (Level.ERROR, Level.CRITICAL))
    return error_count > threshold

def fire_webhook(
    webhook_url: str,
    source_name: str,
    lines: list["LogLine"],
    groups: list["Group"],
    threshold: int,
) -> bool:
    """POST a JSON alert payload to webhook_url. Returns True on success."""
    from .parser import Level
    import urllib.request
    import urllib.error

    error_count = sum(1 for l in lines if l.level in (Level.ERROR, Level.CRITICAL))
    warn_count = sum(1 for l in lines if l.level == Level.WARNING)
    top_patterns = [
        {"count": g.count, "sample": g.lines[0].raw[:200] if g.lines else ""}
        for g in groups[:5]
        if any(l.level in (Level.ERROR, Level.CRITICAL) for l in g.lines)
    ]

    payload = {
        "source": source_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert": "error_threshold_exceeded",
        "threshold": threshold,
        "error_count": error_count,
        "warning_count": warn_count,
        "total_lines": len(lines),
        "top_error_patterns": top_patterns,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "logsift/1.5.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except urllib.error.URLError:
        return False
