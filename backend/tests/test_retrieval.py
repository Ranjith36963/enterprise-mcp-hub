"""Pillar 2 Batch 2.7 — tests for RRF + hybrid retrieval."""
from __future__ import annotations

import pytest

from src.services.retrieval import (
    is_hybrid_available,
    reciprocal_rank_fusion,
    retrieve_for_user,
)


# ---------------------------------------------------------------------------
# RRF — pure helper
# ---------------------------------------------------------------------------


def test_rrf_single_list_preserves_order():
    result = reciprocal_rank_fusion([[1, 2, 3]], k=60)
    ids = [x[0] for x in result]
    assert ids == [1, 2, 3]


def test_rrf_fuses_two_lists_with_common_item():
    """Item appearing in both lists scores higher than items in one only."""
    list_a = [1, 2, 3]
    list_b = [4, 2, 5]   # 2 appears in both, at rank 0 and rank 1
    result = reciprocal_rank_fusion([list_a, list_b], k=60)
    ids = [x[0] for x in result]
    # '2' should land top because it accumulates from both lists.
    assert ids[0] == 2


def test_rrf_respects_rank_position():
    """Rank-1 contribution > rank-10 contribution within the same list."""
    list_a = ["rank0"] + [f"pad_{i}" for i in range(9)] + ["rank10"]
    result = reciprocal_rank_fusion([list_a], k=60)
    scores = dict(result)
    assert scores["rank0"] > scores["rank10"]


def test_rrf_handles_empty_lists():
    assert reciprocal_rank_fusion([[]]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_k_controls_smoothing():
    """Smaller k → rank differences matter more. Larger k → flatter curve."""
    list_a = [10, 20]
    sharp = reciprocal_rank_fusion([list_a], k=1)
    flat = reciprocal_rank_fusion([list_a], k=1000)
    sharp_ratio = sharp[0][1] / sharp[1][1]
    flat_ratio = flat[0][1] / flat[1][1]
    assert sharp_ratio > flat_ratio


def test_rrf_is_deterministic():
    """Same input → same output (stable sort)."""
    lists = [[1, 2, 3], [3, 2, 4]]
    out1 = reciprocal_rank_fusion(lists, k=60)
    out2 = reciprocal_rank_fusion(lists, k=60)
    assert out1 == out2


def test_rrf_rejects_non_positive_k():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[1]], k=0)
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[1]], k=-5)


# ---------------------------------------------------------------------------
# retrieve_for_user — orchestrator
# ---------------------------------------------------------------------------


def test_retrieve_for_user_requires_keyword_fn():
    with pytest.raises(ValueError):
        retrieve_for_user(profile=object())


def test_retrieve_for_user_keyword_only_when_no_semantic():
    """No semantic_fn → returns keyword results truncated to k."""
    def kw(profile, limit):
        return list(range(500))

    result = retrieve_for_user(profile=object(), k=10, keyword_fn=kw)
    assert result == list(range(10))


def test_retrieve_for_user_returns_empty_when_keyword_empty():
    """Nothing to fuse → empty result even if semantic has hits."""
    def kw(profile, limit):
        return []
    def sem(profile, limit):
        return [1, 2, 3]

    result = retrieve_for_user(
        profile=object(), k=10, keyword_fn=kw, semantic_fn=sem,
    )
    assert result == []


def test_retrieve_for_user_fuses_when_semantic_available():
    """Both paths present → RRF-fused result."""
    def kw(profile, limit):
        return [1, 2, 3, 4]
    def sem(profile, limit):
        return [4, 3, 5, 6]

    result = retrieve_for_user(
        profile=object(), k=10, keyword_fn=kw, semantic_fn=sem,
    )
    # Items appearing in both (3, 4) should outrank items in one only.
    assert set(result[:2]) == {3, 4}
    assert set(result) == {1, 2, 3, 4, 5, 6}


def test_retrieve_for_user_falls_back_when_semantic_empty():
    """Semantic returned [] → keyword-only path."""
    def kw(profile, limit):
        return [1, 2, 3]
    def sem(profile, limit):
        return []

    result = retrieve_for_user(
        profile=object(), k=10, keyword_fn=kw, semantic_fn=sem,
    )
    assert result == [1, 2, 3]


def test_retrieve_for_user_falls_back_when_semantic_raises():
    """Semantic exception must not bubble — fall back silently."""
    def kw(profile, limit):
        return [1, 2, 3]
    def sem(profile, limit):
        raise RuntimeError("chroma down")

    result = retrieve_for_user(
        profile=object(), k=10, keyword_fn=kw, semantic_fn=sem,
    )
    assert result == [1, 2, 3]


def test_retrieve_for_user_respects_k():
    def kw(profile, limit):
        return list(range(500))
    def sem(profile, limit):
        return list(range(500))

    result = retrieve_for_user(
        profile=object(), k=50, keyword_fn=kw, semantic_fn=sem,
    )
    assert len(result) == 50


# ---------------------------------------------------------------------------
# is_hybrid_available gate
# ---------------------------------------------------------------------------


def test_is_hybrid_available_true_when_count_positive():
    assert is_hybrid_available(1) is True
    assert is_hybrid_available(1000) is True


def test_is_hybrid_available_false_when_empty():
    assert is_hybrid_available(0) is False


def test_is_hybrid_available_handles_negative_defensively():
    """A negative count is nonsense but shouldn't crash — degrade to False."""
    assert is_hybrid_available(-1) is False
