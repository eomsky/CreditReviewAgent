"""Retrieval-only evaluation metrics, separated from answer generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RetrievalMetrics:
    hit_at_k: float
    recall_at_k: float
    mrr: float


def evaluate_rankings(rankings: list[list[str]], relevant: list[set[str]], k: int) -> RetrievalMetrics:
    if len(rankings) != len(relevant) or not rankings:
        raise ValueError("rankings and relevant must have the same non-zero length")
    hits = recalls = reciprocal = 0.0
    for ranked, truth in zip(rankings, relevant, strict=True):
        top = ranked[:k]
        matched = truth.intersection(top)
        hits += bool(matched)
        recalls += len(matched) / max(len(truth), 1)
        reciprocal += next((1 / (index + 1) for index, item in enumerate(top) if item in truth), 0.0)
    count = len(rankings)
    return RetrievalMetrics(hits / count, recalls / count, reciprocal / count)
