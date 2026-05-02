"""Tests for the async log fetcher."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from logsift.fetcher import load_sources, read_file_lines


def test_read_local_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write("ERROR line one\nINFO line two\nWARN line three\n")
        path = Path(f.name)

    lines = asyncio.run(read_file_lines(path))
    assert lines == ["ERROR line one", "INFO line two", "WARN line three"]
    path.unlink()


def test_load_sources_single_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write("ERROR something broke\nINFO all good\n")
        path = Path(f.name)

    results = asyncio.run(load_sources([path], [], False))
    assert len(results) == 1
    name, lines = results[0]
    assert str(path) in name
    assert "ERROR something broke" in lines
    path.unlink()


def test_load_sources_multiple_files():
    paths = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(f"ERROR file {i} error\n")
            paths.append(Path(f.name))

    results = asyncio.run(load_sources(paths, [], False))
    assert len(results) == 3

    for p in paths:
        p.unlink()


def test_load_sources_no_input_returns_empty():
    results = asyncio.run(load_sources([], [], False))
    assert results == []


def test_load_sources_invalid_url_raises():
    with pytest.raises(Exception):
        asyncio.run(load_sources([], ["http://localhost:1/nonexistent.log"], False, timeout=2.0))
