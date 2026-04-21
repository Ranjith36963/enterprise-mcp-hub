"""Pillar 2 Batch 2.7 — hybrid retrieval with Reciprocal Rank Fusion.

Two signals combined via RRF:

  Stage A — keyword: existing SQL scorer's top-500 by ``match_score``.
  Stage B — semantic: ChromaDB nearest-neighbour on the user profile text.

Stage C — ``reciprocal_rank_fusion(ranked_lists, k=60)`` merges the
per-source rankings without needing score calibration between the two.

When embeddings are unavailable (Chroma empty or ``sentence_transformers``
not installed), the retrieval gracefully falls back to keyword-only.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("job360.services.retrieval")


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion — pure function
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: Iterable[list[Any]],
    k: int = 60,
) -> list[tuple[Any, float]]:
    """Fuse multiple ranked lists into one ranked list via RRF.

    For each list, an item at rank `i` (0-indexed) contributes
    ``1 / (k + i + 1)`` to its running RRF score. Items appearing in
    multiple lists accumulate; the output is sorted by descending score.

    Args:
        ranked_lists: iterable of lists — each list is ordered best → worst.
        k: smoothing constant. Plan §4 Batch 2.7 pins ``k=60`` (the Cormack
            2009 default).

    Returns:
        List of ``(item, score)`` tuples in descending score order.
        Preserves first-appearance-order across ranked_lists as a stable
        tiebreaker when two items score identically.
    """
    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[Any, float] = {}
    first_seen_index: dict[Any, tuple[int, int]] = {}
    for list_index, ranked in enumerate(ranked_lists):
        for rank, item in enumerate(ranked):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
            if item not in first_seen_index:
                first_seen_index[item] = (list_index, rank)

    # Sort descending by score, tiebreaker = first appearance (stable).
    return sorted(
        scores.items(),
        key=lambda kv: (-kv[1], first_seen_index[kv[0]]),
    )


# ---------------------------------------------------------------------------
# Retrieval orchestrator
# ---------------------------------------------------------------------------


def retrieve_for_user(
    profile,
    *,
    k: int = 100,
    keyword_fn: Optional[Callable[[Any, int], list[int]]] = None,
    semantic_fn: Optional[Callable[[Any, int], list[int]]] = None,
    rrf_k: int = 60,
) -> list[int]:
    """Return the top-`k` fused job ids for a user profile.

    This is sync-friendly (pure orchestration) — the upstream fetchers are
    injected via ``keyword_fn`` and ``semantic_fn``. Callers from FastAPI
    or ARQ pass their own wrappers that hit SQLite + ChromaDB.

    Args:
        profile: a ``UserProfile`` — passed through to both fetchers.
        k: how many ids to return after fusion.
        keyword_fn: ``(profile, limit) -> list[int]`` of top keyword-matched
            job ids. Required — this is the always-available path.
        semantic_fn: ``(profile, limit) -> list[int]`` of semantically
            closest job ids. Optional — when None or it returns [],
            retrieval degrades to keyword-only.
        rrf_k: RRF smoothing constant (default 60).

    Returns:
        List of job ids, best first. Length up to ``k``.
    """
    if keyword_fn is None:
        raise ValueError("keyword_fn is required")

    # Stage A — keyword top 500.
    keyword_ids = keyword_fn(profile, 500)
    if not keyword_ids:
        # Nothing to fuse. Bail early — semantic results alone would
        # produce rankings with no keyword corroboration.
        return []

    # Stage B — semantic top 500 (when available).
    semantic_ids: list[int] = []
    if semantic_fn is not None:
        try:
            semantic_ids = semantic_fn(profile, 500)
        except Exception as e:
            logger.warning("Semantic retrieval failed — falling back to keyword: %s", e)
            semantic_ids = []

    if not semantic_ids:
        return keyword_ids[:k]

    # Stage C — RRF fusion.
    fused = reciprocal_rank_fusion([keyword_ids, semantic_ids], k=rrf_k)
    return [item for item, _score in fused[:k]]


def is_hybrid_available(vector_index_count: int) -> bool:
    """Return True if the hybrid path has a populated vector index.

    API routes use this to decide whether ``?mode=hybrid`` is the default
    or whether to fall back to ``?mode=keyword`` when Chroma is empty.
    """
    return vector_index_count > 0
