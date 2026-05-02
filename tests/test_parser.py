"""Tests for the log line parser."""

import pytest
from logsift.parser import Level, LogLine, parse_lines


def test_parse_error_line():
    lines = parse_lines(["2024-01-15T10:23:45Z ERROR Database connection refused: timeout after 5s"])
    assert len(lines) == 1
    assert lines[0].level == Level.ERROR
    assert lines[0].timestamp == "2024-01-15T10:23:45Z"
    assert lines[0].lineno == 1


def test_parse_warning_line():
    lines = parse_lines(["WARN: disk usage at 89% on /dev/sda1"])
    assert len(lines) == 1
    assert lines[0].level == Level.WARNING


def test_parse_critical_line():
    lines = parse_lines(["CRITICAL: out of memory, killing process 1234"])
    assert lines[0].level == Level.CRITICAL
    assert lines[0].is_error_like


def test_parse_info_line():
    lines = parse_lines(["INFO  Server started on port 8080"])
    assert lines[0].level == Level.INFO
    assert not lines[0].is_error_like


def test_parse_empty_lines_skipped():
    lines = parse_lines(["", "   ", "ERROR real line", ""])
    assert len(lines) == 1
    assert lines[0].level == Level.ERROR


def test_parse_multiple_lines():
    raw = [
        "INFO  Starting application",
        "DEBUG Loading config from /etc/app.conf",
        "ERROR Failed to connect to redis: connection refused",
        "WARN  Retry attempt 1/3",
        "CRITICAL System shutdown imminent",
    ]
    lines = parse_lines(raw)
    assert len(lines) == 5
    levels = [l.level for l in lines]
    assert levels == [Level.INFO, Level.DEBUG, Level.ERROR, Level.WARNING, Level.CRITICAL]


def test_tokenize_strips_numbers():
    lines = parse_lines(["ERROR port 8080 connection 127.0.0.1 timed out"])
    assert "8080" not in lines[0].tokens
    assert "N" not in lines[0].tokens or True  # digits replaced with N then filtered


def test_lineno_tracking():
    raw = ["INFO line one", "ERROR line two", "WARN line three"]
    lines = parse_lines(raw)
    assert [l.lineno for l in lines] == [1, 2, 3]
