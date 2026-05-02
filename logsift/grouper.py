"""Cluster similar log lines using TF-IDF bag-of-words vectors and cosine similarity."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from .parser import LogLine


@dataclass
class Group:
    label: str
    lines: list[LogLine] = field(default_factory=list)
    centroid: np.ndarray | None = field(default=None, repr=False)

    @property
    def count(self) -> int:
        return len(self.lines)

    @property
    def sample(self) -> str:
        return self.lines[0].raw if self.lines else ""


def _build_tfidf(lines: list[LogLine]) -> tuple[np.ndarray, list[str]]:
    """Return (matrix [n_docs x vocab], vocab) for the given log lines."""
    vocab_counts: Counter[str] = Counter()
    for line in lines:
        vocab_counts.update(set(line.tokens))

    vocab = [t for t, _ in vocab_counts.most_common(512)]
    vocab_index = {t: i for i, t in enumerate(vocab)}
    n = len(lines)
    v = len(vocab)

    tf = np.zeros((n, v), dtype=np.float32)
    for i, line in enumerate(lines):
        c = Counter(line.tokens)
        total = max(sum(c.values()), 1)
        for tok, cnt in c.items():
            if tok in vocab_index:
                tf[i, vocab_index[tok]] = cnt / total

    df = np.count_nonzero(tf, axis=0).astype(np.float32)
    idf = np.log((n + 1) / (df + 1)) + 1.0

    tfidf = tf * idf
    norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    tfidf /= norms
    return tfidf, vocab


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def group_lines(lines: list[LogLine], threshold: float = 0.45) -> list[Group]:
    """Group similar log lines by cosine similarity on TF-IDF vectors."""
    if not lines:
        return []

    lines_with_tokens = [l for l in lines if l.tokens]
    lines_no_tokens = [l for l in lines if not l.tokens]

    if not lines_with_tokens:
        g = Group(label="(unparseable)")
        g.lines = lines_no_tokens
        return [g]

    tfidf, _vocab = _build_tfidf(lines_with_tokens)

    groups: list[Group] = []
    assignments: list[int] = [-1] * len(lines_with_tokens)

    for i, line in enumerate(lines_with_tokens):
        vec = tfidf[i]
        best_group = -1
        best_sim = threshold

        for gi, g in enumerate(groups):
            if g.centroid is not None:
                sim = _cosine(vec, g.centroid)
                if sim > best_sim:
                    best_sim = sim
                    best_group = gi

        if best_group == -1:
            g = Group(label=_make_label(line), centroid=vec.copy())
            groups.append(g)
            best_group = len(groups) - 1

        groups[best_group].lines.append(line)
        assignments[i] = best_group
        # Update centroid with running mean
        n = groups[best_group].count
        c = groups[best_group].centroid
        groups[best_group].centroid = c + (vec - c) / n
        norm = np.linalg.norm(groups[best_group].centroid)
        if norm > 0:
            groups[best_group].centroid /= norm

    if lines_no_tokens:
        g = Group(label="(other)")
        g.lines = lines_no_tokens
        groups.append(g)

    groups.sort(key=lambda g: g.count, reverse=True)
    return groups


def _make_label(line: LogLine) -> str:
    """Create a short human-readable label from the first few meaningful tokens."""
    tokens = line.tokens[:6]
    return ' '.join(tokens) if tokens else line.raw[:60]
