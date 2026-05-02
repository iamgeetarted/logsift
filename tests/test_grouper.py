"""Tests for the log line grouper."""

import pytest
from logsift.grouper import group_lines
from logsift.parser import parse_lines


def _make_lines(texts: list[str]):
    return parse_lines(texts)


def test_identical_lines_same_group():
    raw = ["ERROR database connection refused"] * 10
    lines = _make_lines(raw)
    groups = group_lines(lines, threshold=0.4)
    assert groups[0].count == 10


def test_different_errors_separate_groups():
    raw = [
        "ERROR database connection refused",
        "ERROR database connection refused",
        "ERROR out of memory kernel panic",
        "ERROR out of memory kernel panic",
        "ERROR disk write failure permission denied",
    ]
    lines = _make_lines(raw)
    groups = group_lines(lines, threshold=0.4)
    assert len(groups) >= 2


def test_empty_input_returns_empty():
    assert group_lines([]) == []


def test_groups_sorted_by_count_descending():
    raw = (
        ["ERROR connection refused"] * 5
        + ["WARN disk space low"] * 3
        + ["INFO server started"] * 1
    )
    lines = _make_lines(raw)
    groups = group_lines(lines, threshold=0.3)
    counts = [g.count for g in groups]
    assert counts == sorted(counts, reverse=True)


def test_group_has_sample():
    lines = _make_lines(["ERROR something broke"])
    groups = group_lines(lines)
    assert groups[0].sample != ""
    assert groups[0].count == 1


def test_high_threshold_more_groups():
    raw = [
        "ERROR db connection refused port 5432",
        "ERROR db connection refused port 5433",
        "ERROR db connection refused port 5434",
    ]
    lines_low = _make_lines(raw)
    lines_high = _make_lines(raw)
    groups_low = group_lines(lines_low, threshold=0.3)
    groups_high = group_lines(lines_high, threshold=0.99)
    assert len(groups_high) >= len(groups_low)
