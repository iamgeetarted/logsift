"""Async fetching of log content from files or remote URLs."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import AsyncIterator

import httpx


async def read_file_lines(path: Path) -> list[str]:
    """Read all lines from a local file asynchronously (via thread pool)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: path.read_text(errors='replace').splitlines())


async def fetch_url_lines(url: str, timeout: float = 30.0) -> list[str]:
    """Fetch text content from a URL and return as lines."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text.splitlines()


async def read_stdin_lines() -> list[str]:
    """Read all lines from stdin via thread pool (non-blocking)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sys.stdin.readlines)


async def load_sources(
    paths: list[Path],
    urls: list[str],
    from_stdin: bool,
    timeout: float = 30.0,
) -> list[tuple[str, list[str]]]:
    """Load all sources concurrently. Returns list of (source_name, lines)."""
    tasks: list[tuple[str, asyncio.Task[list[str]]]] = []

    async with asyncio.TaskGroup() as tg:
        for path in paths:
            t = tg.create_task(read_file_lines(path))
            tasks.append((str(path), t))
        for url in urls:
            t = tg.create_task(fetch_url_lines(url, timeout=timeout))
            tasks.append((url, t))
        if from_stdin:
            t = tg.create_task(read_stdin_lines())
            tasks.append(("<stdin>", t))

    return [(name, task.result()) for name, task in tasks]
