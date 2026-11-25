"""Hybrid keyword + semantic search over synced source records.

Designed to work completely offline with zero external API dependencies by default
(via deterministic hashed n-gram embeddings), while remaining pluggable via the
``TextEmbedder`` protocol for future dense embedding models.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from context_substrate.models import SourceRecord

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class TextEmbedder(Protocol):
    """Protocol for converting text into a normalized dense vector."""

    def embed(self, text: str) -> list[float]: ...


class HashedNgramEmbedder:
    """Deterministic offline embedder using hashed word + character 3-gram features.

    Produces L2-normalized vectors so cosine similarity is a simple dot product.
    Captures both word overlap and subword/morphological similarity (e.g. "career"
    vs "careers", "deciding" vs "decision") without requiring external ML weights.
    """

    def __init__(self, dims: int = 256) -> None:
        self._dims = dims

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        tokens = _tokenize(text)
        if not tokens:
            return vec

        features: list[tuple[str, float]] = []
        for tok in tokens:
            features.append((f"w:{tok}", 2.0))
            padded = f"^{tok}$"
            if len(padded) >= 3:
                for i in range(len(padded) - 2):
                    features.append((f"c:{padded[i : i + 3]}", 1.0))

        for i in range(len(tokens) - 1):
            features.append((f"b:{tokens[i]}_{tokens[i + 1]}", 1.5))

        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self._dims
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign * weight

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [v / norm for v in vec]
        return vec


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return max(0.0, min(1.0, dot))


def _record_text(record: SourceRecord) -> str:
    if record.thread_title:
        return f"{record.thread_title}\n{record.content}"
    return record.content


@dataclass(frozen=True, slots=True)
class RankedHit:
    score: float
    record: SourceRecord


def hybrid_rank(
    query: str,
    records: list[SourceRecord],
    *,
    embedder: TextEmbedder | None = None,
    semantic_weight: float = 0.5,
    limit: int = 15,
    min_score: float = 0.05,
) -> list[RankedHit]:
    """Rank candidate records using a hybrid of keyword + semantic similarity."""
    query_stripped = query.strip()
    if not query_stripped or not records:
        return []

    active_embedder = embedder or HashedNgramEmbedder()
    query_tokens = _tokenize(query_stripped)
    query_token_set = set(query_tokens)
    query_lower = query_stripped.lower()
    query_vec = active_embedder.embed(query_stripped)

    # Document frequency for IDF weighting across the candidate set.
    doc_tokens_list = [_tokenize(_record_text(r)) for r in records]
    num_docs = len(records)
    df: Counter[str] = Counter()
    for doc_tokens in doc_tokens_list:
        for tok in set(doc_tokens):
            df[tok] += 1

    kw_weight = 1.0 - semantic_weight
    hits: list[RankedHit] = []

    for record, doc_tokens in zip(records, doc_tokens_list, strict=True):
        if record.deleted:
            continue

        text = _record_text(record)
        if not text.strip():
            continue

        # 1. Keyword score (IDF-weighted coverage + exact phrase bonus)
        kw_score = 0.0
        if query_token_set and doc_tokens:
            doc_counts = Counter(doc_tokens)
            total_idf = 0.0
            matched_idf = 0.0
            for qtok in query_token_set:
                idf = math.log((num_docs + 1) / (df.get(qtok, 0) + 1)) + 1.0
                total_idf += idf
                if qtok in doc_counts:
                    # Diminishing returns for repeated occurrences
                    tf_boost = min(1.0, 0.7 + 0.3 * math.log1p(doc_counts[qtok]))
                    matched_idf += idf * tf_boost
            if total_idf > 0.0:
                kw_score = matched_idf / total_idf
            if len(query_lower) >= 3 and query_lower in text.lower():
                kw_score = min(1.0, kw_score + 0.2)

        # 2. Semantic score (cosine similarity on embedder vectors)
        doc_vec = active_embedder.embed(text)
        sem_score = _cosine_similarity(query_vec, doc_vec)

        combined = kw_weight * kw_score + semantic_weight * sem_score
        if combined >= min_score:
            hits.append(RankedHit(score=round(min(1.0, combined), 4), record=record))

    hits.sort(
        key=lambda h: (h.score, h.record.created_at.timestamp(), h.record.id),
        reverse=True,
    )
    return hits[:limit]
