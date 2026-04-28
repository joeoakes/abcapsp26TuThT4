"""
test_rag_maze.py
Automated test runner for rag_maze.py — covers all 25 test cases (4.1–4.25).

Run from the project root:
    python test_runners/test_rag_maze.py
"""
from __future__ import annotations

import sys, os, time, threading, tracemalloc
import unittest.mock as mock
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'project_src'))
from test_framework import TestSuite  # noqa: E402

# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------
try:
    import fakeredis
    def _make_redis(): return fakeredis.FakeRedis(decode_responses=True)
except ImportError:
    # Reuse the stub from test_maze_redis
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    exec(open(os.path.join(os.path.dirname(__file__), "test_maze_redis.py"))
         .read().split("import importlib")[0])   # pull in _FakeRedis class
    def _make_redis(): return _FakeRedis()  # type: ignore

import importlib
rag_maze = importlib.import_module("rag_maze")

VDIM = rag_maze.VECTOR_DIM  # 7

def _summary(**kw):
    base = {
        "moves_left_turn": 2, "moves_right_turn": 3,
        "moves_straight": 4,  "moves_reverse": 1,
        "moves_total": 10,
        "duration_seconds": 60,
        "distance_traveled": 5.0,
        "mission_result": "success",
    }
    base.update(kw)
    return base


def _open_maze(w, h):
    cells = [15] * (w * h)
    for y in range(h):
        for x in range(w):
            if x < w - 1:
                cells[y * w + x] &= ~2
                cells[y * w + x + 1] &= ~8
            if y < h - 1:
                cells[y * w + x] &= ~4
                cells[(y + 1) * w + x] &= ~1
    return cells

# ---------------------------------------------------------------------------
suite = TestSuite("rag_maze.py")

# 4.1
def _t41():
    assert rag_maze._normalize_mission_result("In Progress") == "in_progress"
    assert rag_maze._normalize_mission_result("SUCCESS") == "success"
suite.run("4.1", "Unit Testing",
          "_normalize_mission_result() – mixed case/spaces handled", _t41)

# 4.2
def _t42():
    assert rag_maze._result_dimension("success")     == 1.0
    assert rag_maze._result_dimension("failed")      == 0.0
    assert rag_maze._result_dimension("in_progress") == 0.5
suite.run("4.2", "Unit Testing",
          "_result_dimension() – maps known results to floats", _t42)

# 4.3
def _t43():
    assert rag_maze._result_dimension("unknown_val") == 0.0
suite.run("4.3", "Unit Testing",
          "_result_dimension() – returns 0.0 for unknown result", _t43)

# 4.4
def _t44():
    v = rag_maze.mission_to_vector(_summary())
    assert v.shape == (VDIM,)
    assert v.dtype == np.float32
suite.run("4.4", "Unit Testing",
          "mission_to_vector() – produces 7-element float32 array", _t44)

# 4.5
def _t45():
    s = _summary(moves_left_turn=2, moves_right_turn=2,
                 moves_straight=2, moves_reverse=2, moves_total=8)
    v = rag_maze.mission_to_vector(s)
    for i in range(4):
        assert abs(v[i] - 0.25) < 1e-5, f"dim {i} = {v[i]}"
suite.run("4.5", "Unit Testing",
          "mission_to_vector() – proportional dims are correct", _t45)

# 4.6
def _t46():
    s = _summary(duration_seconds=rag_maze.MAX_DURATION * 2)
    v = rag_maze.mission_to_vector(s)
    assert v[4] == 1.0
suite.run("4.6", "Unit Testing",
          "mission_to_vector() – duration capped at 1.0", _t46)

# 4.7
def _t47():
    s = _summary(moves_total=0)
    v = rag_maze.mission_to_vector(s)
    assert v.shape == (VDIM,), "Should not raise ZeroDivisionError"
suite.run("4.7", "Unit Testing",
          "mission_to_vector() – zero moves_total no divide-by-zero", _t47)

# 4.8
def _t48():
    v = np.random.rand(VDIM).astype(np.float32)
    enc = rag_maze._vec_to_stored(v)
    dec = rag_maze._stored_to_vec(enc)
    assert np.allclose(v, dec, atol=1e-6)
suite.run("4.8", "Unit Testing",
          "_vec_to_stored() / _stored_to_vec() round-trip", _t48)

# 4.9
def _t49():
    v = np.array([1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    assert abs(rag_maze.cosine_similarity(v, v) - 1.0) < 1e-6
suite.run("4.9", "Unit Testing",
          "cosine_similarity() – identical vectors return 1.0", _t49)

# 4.10
def _t410():
    a = np.array([1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    b = np.array([0, 1, 0, 0, 0, 0, 0], dtype=np.float32)
    assert abs(rag_maze.cosine_similarity(a, b)) < 1e-6
suite.run("4.10", "Unit Testing",
          "cosine_similarity() – orthogonal vectors return 0.0", _t410)

# 4.11
def _t411():
    z = np.zeros(VDIM, dtype=np.float32)
    v = np.ones(VDIM, dtype=np.float32)
    assert rag_maze.cosine_similarity(z, v) == 0.0
suite.run("4.11", "Unit Testing",
          "cosine_similarity() – zero vector returns 0.0", _t411)

# 4.12
def _t412():
    r = _make_redis()
    vec = rag_maze.store_mission_vector(r, "m1", _summary())
    data = r.hgetall("mission:m1:vector")
    assert "embedding"  in data
    assert "robot_id"   in data
    assert "moves_total" in data
suite.run("4.12", "Unit Testing",
          "store_mission_vector() – writes hash fields to Redis", _t412)

# 4.13
def _t413():
    assert rag_maze.build_rag_context([]) == ""
suite.run("4.13", "Unit Testing",
          "build_rag_context() – empty list returns empty string", _t413)

# 4.14
def _t414():
    missions = [
        ("m1", 0.9, _summary(moves_total=10, mission_result="success")),
        ("m2", 0.8, _summary(moves_total=20, mission_result="success")),
    ]
    ctx = rag_maze.build_rag_context(missions)
    assert "15" in ctx, f"Expected avg 15 in:\n{ctx}"
suite.run("4.14", "Unit Testing",
          "build_rag_context() – computes avg moves for successful missions", _t414)

# 4.15
def _t415():
    missions = [
        ("m1", 0.9, _summary(moves_total=10, mission_result="success")),
        ("m2", 0.8, _summary(moves_total=20, mission_result="failed")),
    ]
    ctx = rag_maze.build_rag_context(missions)
    assert "successful" in ctx
    assert "failed" in ctx
suite.run("4.15", "Unit Testing",
          "build_rag_context() – separate avgs for success and failed", _t415)

# 4.16
def _t416():
    r = _make_redis()
    # Store 3 distinct vectors
    v_target = np.array([0.5, 0.1, 0.1, 0.1, 0.0, 0.0, 1.0], dtype=np.float32)
    for i, v in enumerate([
        np.array([0.0]*VDIM, dtype=np.float32),
        v_target,
        np.array([1.0]*VDIM, dtype=np.float32),
    ]):
        key = f"mission:m{i}:vector"
        r.hset(key, mapping={"embedding": rag_maze._vec_to_stored(v)})

    results = rag_maze._search_fallback(r, v_target, top_k=1)
    assert len(results) == 1
    assert abs(results[0][1] - 1.0) < 0.01, f"Expected similarity≈1.0, got {results[0][1]}"
suite.run("4.16", "Integration Testing",
          "store_mission_vector → _search_fallback retrieves correct top-1", _t416)

# 4.17
def _t417():
    r = _make_redis()
    for i in range(5):
        rag_maze.store_mission_vector(r, f"mis{i}", _summary(mission_result="success"))
        r.hset(f"mission:mis{i}:summary", mapping={"mission_result": "success", "moves_total": "10"})
    with mock.patch.object(rag_maze, "has_redisearch", return_value=False):
        ctx = rag_maze.retrieve_rag_context(r, _summary(), top_k=3)
    assert isinstance(ctx, str)
    assert len(ctx) > 0
suite.run("4.17", "Integration Testing",
          "retrieve_rag_context() end-to-end with fallback backend", _t417)

# 4.18
def _t418():
    r = _make_redis()
    with mock.patch.object(rag_maze, "has_redisearch", return_value=False):
        result = rag_maze.ensure_index(r)
    assert result is False  # no RediSearch → returns False
suite.run("4.18", "Integration Testing",
          "ensure_index() – returns False without RediSearch module", _t418)

# 4.19 – Verify _search_redisearch catches FT.SEARCH errors and calls _search_fallback.
# We patch _search_fallback directly to confirm it gets called when execute_command fails.
def _t419():
    r = _make_redis()
    v = np.ones(VDIM, dtype=np.float32)
    r.hset("mission:fb19:vector", mapping={"embedding": rag_maze._vec_to_stored(v)})
    original_exec = r.execute_command

    fallback_called = []
    original_fallback = rag_maze._search_fallback
    def spy_fallback(redis, qv, top_k):
        fallback_called.append(True)
        return original_fallback(redis, qv, top_k)

    # Only raise on FT.SEARCH commands, pass through SCAN/others
    def selective_boom(cmd, *args, **kw):
        if cmd == "FT.SEARCH":
            raise Exception("FT error")
        return original_exec(cmd, *args, **kw)

    with mock.patch.object(rag_maze, "_search_fallback", side_effect=spy_fallback):
        r.execute_command = selective_boom
        results = rag_maze._search_redisearch(r, np.zeros(VDIM, dtype=np.float32), top_k=3)
        r.execute_command = original_exec

    assert fallback_called, "_search_fallback was never called after FT.SEARCH error"
    assert isinstance(results, list)
suite.run("4.19", "Integration Testing",
          "_search_redisearch() falls back to Python on query error", _t419)

# 4.20
def _t420():
    r = _make_redis()
    for i in range(1000):
        v = np.random.rand(VDIM).astype(np.float32)
        r.hset(f"mission:bulk_{i}:vector",
               mapping={"embedding": rag_maze._vec_to_stored(v)})
    query = np.random.rand(VDIM).astype(np.float32)
    t0 = time.perf_counter()
    results = rag_maze._search_fallback(r, query, top_k=5)
    elapsed = time.perf_counter() - t0
    assert len(results) == 5
    assert elapsed < 5.0, f"Retrieval took {elapsed:.2f}s"
suite.run("4.20", "System Testing",
          "Retrieve top-5 from 1,000 vectors – latency < 5s", _t420)

# 4.21
def _t421():
    r = _make_redis()
    for i in range(20):
        rag_maze.store_mission_vector(r, f"cmp_{i}", _summary())
    query = rag_maze.mission_to_vector(_summary())
    fb = rag_maze._search_fallback(r, query, top_k=5)
    assert len(fb) <= 5
suite.run("4.21", "System Testing",
          "Fallback search returns ≤ top_k results", _t421)

# 4.22
def _t422():
    import importlib as il
    m = il.import_module("rag_maze")
    assert hasattr(m, "mission_to_vector")
    assert hasattr(m, "retrieve_rag_context")
suite.run("4.22", "Smoke Testing", "Module imports without error", _t422)

# 4.23
def _t423():
    r = _make_redis()
    with mock.patch.object(rag_maze, "has_redisearch", return_value=False):
        ctx = rag_maze.retrieve_rag_context(r, _summary())
    assert ctx == ""
suite.run("4.23", "Smoke Testing",
          "retrieve_rag_context() with empty Redis returns empty string", _t423)

# 4.24
def _t424():
    r = _make_redis()
    errors = []
    def worker(i):
        try:
            rag_maze.store_mission_vector(r, f"conc_{i}", _summary())
        except Exception as e:
            errors.append(str(e))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == [], f"Thread errors: {errors[:3]}"
suite.run("4.24", "Stress/Load Testing",
          "100 concurrent store_mission_vector() calls – no errors", _t424)

# 4.25
def _t425():
    a = np.random.rand(VDIM).astype(np.float32)
    b = np.random.rand(VDIM).astype(np.float32)
    t0 = time.perf_counter()
    for _ in range(10_000):
        rag_maze.cosine_similarity(a, b)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"10k cosine calls took {elapsed:.2f}s"
suite.run("4.25", "Stress/Load Testing",
          "10,000 cosine_similarity() calls – throughput < 2s", _t425)


# 4.26
def _t426():
    cells = _open_maze(4, 4)
    vec = rag_maze._maze_structure_vector(4, 4, cells)
    assert vec.shape == (rag_maze.TRAJECTORY_VEC_DIM,)
    assert vec.dtype == np.float32


suite.run("4.26", "Unit Testing",
          "_maze_structure_vector() returns fixed-size embedding", _t426)


# 4.27
def _t427():
    r = _make_redis()
    cells = _open_maze(4, 4)
    key = rag_maze.store_successful_trajectory(
        r=r,
        maze_sig="abc123",
        width=4,
        height=4,
        cells=cells,
        plan=["RIGHT", "DOWN", "RIGHT"],
        mission_result="success",
    )
    assert key is not None
    stored = r.hgetall(key)
    assert stored.get("maze_sig") == "abc123"
    assert "embedding" in stored and "plan" in stored


suite.run("4.27", "Integration Testing",
          "store_successful_trajectory() writes trajectory record", _t427)


# 4.28
def _t428():
    r = _make_redis()
    cells_a = _open_maze(4, 4)
    cells_b = _open_maze(4, 4)
    rag_maze.store_successful_trajectory(
        r, "maze_a", 4, 4, cells_a, ["RIGHT", "RIGHT", "DOWN"], "success"
    )
    rag_maze.store_successful_trajectory(
        r, "maze_b", 4, 4, cells_b, ["DOWN", "DOWN", "RIGHT"], "success"
    )
    snippets = rag_maze.retrieve_similar_trajectories(
        r=r,
        maze_sig="maze_a",
        width=4,
        height=4,
        cells=cells_a,
        top_k=2,
        prefix_len=2,
    )
    assert len(snippets) >= 1
    top = snippets[0]
    assert top[2] == "maze_a"
    assert top[0] >= 0.99
    assert len(top[1]) == 2


suite.run("4.28", "Integration Testing",
          "retrieve_similar_trajectories() prioritizes exact maze_sig", _t428)

# ---------------------------------------------------------------------------
suite.print_summary()
sys.exit(suite.exit_code())
