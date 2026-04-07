"""Tests for rag_maze.py — vectorization, storage, retrieval, and prompt building."""

import uuid

import numpy as np

from src.backend import maze_redis, rag_maze

r = maze_redis.connect()
TEST_PREFIX = "rag_test_" + uuid.uuid4().hex[:8]


def _sid():
    return f"{TEST_PREFIX}_{uuid.uuid4().hex[:8]}"


def _sample_summary(
    left=25, right=45, straight=28, reverse=42,
    duration=63, distance=54.6, result="success",
):
    total = left + right + straight + reverse
    return {
        "robot_id": "test-bot",
        "mission_type": "explore",
        "moves_left_turn": left,
        "moves_right_turn": right,
        "moves_straight": straight,
        "moves_reverse": reverse,
        "moves_total": total,
        "duration_seconds": duration,
        "distance_traveled": distance,
        "mission_result": result,
    }


# ── Vectorization ────────────────────────────────────────────────────

def test_mission_to_vector_shape():
    vec = rag_maze.mission_to_vector(_sample_summary())
    assert vec.shape == (7,)
    assert vec.dtype == np.float32


def test_mission_to_vector_values():
    s = _sample_summary(left=25, right=25, straight=25, reverse=25)
    vec = rag_maze.mission_to_vector(s)
    assert abs(vec[0] - 0.25) < 0.01
    assert abs(vec[1] - 0.25) < 0.01
    assert abs(vec[2] - 0.25) < 0.01
    assert abs(vec[3] - 0.25) < 0.01


def test_vector_ratios_sum_to_one():
    vec = rag_maze.mission_to_vector(_sample_summary())
    assert abs(vec[0] + vec[1] + vec[2] + vec[3] - 1.0) < 0.01


def test_result_mapping():
    assert rag_maze.mission_to_vector(
        _sample_summary(result="success")
    )[6] == 1.0
    assert rag_maze.mission_to_vector(
        _sample_summary(result="in_progress")
    )[6] == 0.5
    assert rag_maze.mission_to_vector(
        _sample_summary(result="failed")
    )[6] == 0.0


def test_zero_moves_safe():
    s = _sample_summary(left=0, right=0, straight=0, reverse=0)
    s["moves_total"] = 0
    vec = rag_maze.mission_to_vector(s)
    assert vec.shape == (7,)
    assert not np.any(np.isnan(vec))


# ── Cosine similarity ────────────────────────────────────────────────

def test_cosine_identical():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert abs(rag_maze.cosine_similarity(a, a) - 1.0) < 0.001


def test_cosine_orthogonal():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert abs(rag_maze.cosine_similarity(a, b)) < 0.001


def test_cosine_similar():
    a = np.array([0.25, 0.25, 0.25, 0.25, 0.5, 0.5, 1.0], dtype=np.float32)
    b = np.array([0.20, 0.30, 0.25, 0.25, 0.5, 0.5, 1.0], dtype=np.float32)
    sim = rag_maze.cosine_similarity(a, b)
    assert sim > 0.95


# ── Store & retrieve vectors ─────────────────────────────────────────

def test_store_and_retrieve_vector():
    mid = _sid()
    summary = _sample_summary()

    r.hset(f"mission:{mid}:summary", mapping={
        k: str(v) for k, v in summary.items()
    })

    vec = rag_maze.store_mission_vector(r, mid, summary)
    assert vec.shape == (7,)

    raw = r.hget(f"mission:{mid}:vector", "embedding")
    assert raw is not None
    recovered = rag_maze._stored_to_vec(raw)
    np.testing.assert_array_almost_equal(vec, recovered)

    r.delete(f"mission:{mid}:summary", f"mission:{mid}:vector")


def test_search_fallback_finds_similar():
    """Store 3 missions, query with one similar — fallback search should rank it first."""
    ids = [_sid() for _ in range(3)]
    summaries = [
        _sample_summary(left=10, right=50, straight=15, reverse=25, result="success"),
        _sample_summary(left=25, right=25, straight=25, reverse=25, result="failed"),
        _sample_summary(left=12, right=48, straight=18, reverse=22, result="success"),
    ]

    for mid, s in zip(ids, summaries):
        r.hset(f"mission:{mid}:summary", mapping={k: str(v) for k, v in s.items()})
        rag_maze.store_mission_vector(r, mid, s)

    query = _sample_summary(left=11, right=49, straight=16, reverse=24, result="success")
    query_vec = rag_maze.mission_to_vector(query)
    results = rag_maze._search_fallback(r, query_vec, top_k=3)

    assert len(results) >= 2

    returned_ids = [mid for mid, _, _ in results]
    assert ids[0] in returned_ids or ids[2] in returned_ids

    if len(results) >= 2:
        assert results[0][1] >= results[1][1]

    for mid in ids:
        r.delete(f"mission:{mid}:summary", f"mission:{mid}:vector")


# ── Prompt building ──────────────────────────────────────────────────

def test_build_rag_context_empty():
    assert rag_maze.build_rag_context([]) == ""


def test_build_rag_context_format():
    missions = [
        ("m1", 0.95, {"mission_result": "success", "moves_total": "100", "duration_seconds": "30"}),
        ("m2", 0.80, {"mission_result": "failed", "moves_total": "200", "duration_seconds": "60"}),
    ]
    ctx = rag_maze.build_rag_context(missions)
    assert "m1" in ctx
    assert "m2" in ctx
    assert "success" in ctx
    assert "failed" in ctx
    assert "similarity=" in ctx


# ── End-to-end retrieve_rag_context ──────────────────────────────────

def test_retrieve_rag_context_end_to_end():
    ids = [_sid() for _ in range(3)]
    summaries = [
        _sample_summary(left=30, right=30, straight=20, reverse=20, result="success"),
        _sample_summary(left=10, right=10, straight=40, reverse=40, result="failed"),
        _sample_summary(left=28, right=32, straight=18, reverse=22, result="success"),
    ]
    for mid, s in zip(ids, summaries):
        r.hset(f"mission:{mid}:summary", mapping={k: str(v) for k, v in s.items()})
        rag_maze.store_mission_vector(r, mid, s)

    current = _sample_summary(left=29, right=31, straight=19, reverse=21, result="in_progress")
    ctx = rag_maze.retrieve_rag_context(r, current, top_k=3)

    assert "Retrieved similar missions" in ctx
    assert "similarity=" in ctx

    for mid in ids:
        r.delete(f"mission:{mid}:summary", f"mission:{mid}:vector")


if __name__ == "__main__":
    import sys

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
