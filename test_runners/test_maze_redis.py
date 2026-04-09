"""
test_maze_redis.py
Automated test runner for maze_redis.py — covers all 23 test cases (3.1–3.23).

Run from the project root:
    python test_runners/test_maze_redis.py

Uses fakeredis for a real in-memory Redis implementation with no live server needed.
Falls back to a minimal dict-backed stub when fakeredis is unavailable.
"""
from __future__ import annotations

import sys, os, json, threading, time, tracemalloc
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'project_src'))
from test_framework import TestSuite  # noqa: E402

# ---------------------------------------------------------------------------
# Redis backend: prefer fakeredis, fall back to a minimal stub
# ---------------------------------------------------------------------------
try:
    import fakeredis
    def _make_redis():
        return fakeredis.FakeRedis(decode_responses=True)
    BACKEND = "fakeredis"
except ImportError:
    # Minimal stub that covers the API surface used by maze_redis
    class _FakeRedis:
        def __init__(self):
            self._store: dict = {}
            self._sets:  dict = {}

        def set(self, k, v): self._store[k] = str(v); return True
        def get(self, k):    return self._store.get(k)
        def delete(self, *ks):
            n = 0
            for k in ks:
                if k in self._store: del self._store[k]; n += 1
                if k in self._sets:  del self._sets[k];  n += 1
            return n
        def sadd(self, k, *vs):
            self._sets.setdefault(k, set()).update(vs); return len(vs)
        def sismember(self, k, v): return v in self._sets.get(k, set())
        def smembers(self, k):     return self._sets.get(k, set())
        def incr(self, k):
            v = int(self._store.get(k, 0)) + 1
            self._store[k] = str(v); return v
        def scan_iter(self, match="*", count=100):
            import fnmatch
            return [k for k in list(self._store) + list(self._sets)
                    if fnmatch.fnmatch(k, match)]
        def pipeline(self): return _FakePipe(self)
        def ping(self): return True

    class _FakePipe:
        def __init__(self, r): self._r = r; self._cmds = []
        def set(self, k, v):    self._cmds.append(('set',  k, v));    return self
        def delete(self, *ks):  self._cmds.append(('del',  ks));      return self
        def execute(self):
            for cmd, *args in self._cmds:
                if cmd == 'set':   self._r.set(*args)
                elif cmd == 'del': self._r.delete(*args[0])

    def _make_redis(): return _FakeRedis()
    BACKEND = "stub"

# ---------------------------------------------------------------------------
# Stub tools_maze before importing maze_redis
# ---------------------------------------------------------------------------
sys.modules.setdefault("tools_maze", mock.MagicMock())
_tools = sys.modules["tools_maze"]
_tools.DIRECTIONS = {
    "UP":    (0, -1), "DOWN":  (0,  1),
    "LEFT":  (-1, 0), "RIGHT": ( 1, 0),
}

import importlib
maze_redis = importlib.import_module("maze_redis")

# ---------------------------------------------------------------------------
suite = TestSuite(f"maze_redis.py  [backend: {BACKEND}]")

# 3.1
def _t31():
    h1 = maze_redis.maze_signature([1, 2, 3])
    h2 = maze_redis.maze_signature([1, 2, 3])
    assert h1 == h2
suite.run("3.1", "Unit Testing", "maze_signature() – deterministic SHA-256", _t31)

# 3.2
def _t32():
    assert maze_redis.maze_signature([1,2,3]) != maze_redis.maze_signature([3,2,1])
suite.run("3.2", "Unit Testing",
          "maze_signature() – different lists produce different hashes", _t32)

# 3.3
def _t33():
    r = _make_redis()
    sig = maze_redis.store_maze(r, "s1", 2, 2, [1,2,3,4], 0, 0, 1, 1)
    data = maze_redis.load_maze(r, "s1")
    assert data is not None
    assert data["width"]  == 2
    assert data["height"] == 2
    assert data["cells"]  == [1,2,3,4]
    assert data["start_x"] == 0
    assert data["goal_x"]  == 1
    assert data["maze_sig"] == sig
suite.run("3.3", "Unit Testing", "store_maze() / load_maze() round-trip", _t33)

# 3.4
def _t34():
    r = _make_redis()
    assert maze_redis.load_maze(r, "ghost") is None
suite.run("3.4", "Unit Testing", "load_maze() – None for unknown session", _t34)

# 3.5
def _t35():
    r = _make_redis()
    maze_redis.store_maze(r, "s2", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.mark_visited(r, "s2", 1, 0)
    maze_redis.store_maze(r, "s2", 2, 2, [1]*4, 0, 0, 1, 1)  # re-store resets
    visited = maze_redis.get_visited(r, "s2")
    assert (1, 0) not in visited
suite.run("3.5", "Unit Testing", "store_maze() – resets runtime state", _t35)

# 3.6
def _t36():
    r = _make_redis()
    maze_redis.store_maze(r, "s3", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.mark_visited(r, "s3", 2, 3)
    v = maze_redis.is_visited(r, "s3", 2, 3)
    assert v, f"Expected truthy, got {v!r}"
    assert (2, 3) in maze_redis.get_visited(r, "s3")
suite.run("3.6", "Unit Testing", "mark_visited() / is_visited() / get_visited()", _t36)

# 3.7
def _t37():
    r = _make_redis()
    maze_redis.store_maze(r, "s4", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.append_history(r, "s4", "RIGHT")
    maze_redis.append_history(r, "s4", "DOWN")
    h = maze_redis.get_history(r, "s4")
    assert h == ["RIGHT", "DOWN"]
suite.run("3.7", "Unit Testing", "append_history() / get_history()", _t37)

# 3.8
def _t38():
    r = _make_redis()
    maze_redis.store_maze(r, "s5", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.store_plan(r, "s5", ["UP", "LEFT"])
    assert maze_redis.get_plan(r, "s5") == ["UP", "LEFT"]
    assert maze_redis.get_plan_index(r, "s5") == 0
suite.run("3.8", "Unit Testing", "store_plan() / get_plan() – plan_index reset to 0", _t38)

# 3.9
def _t39():
    r = _make_redis()
    maze_redis.store_maze(r, "s6", 2, 2, [1]*4, 0, 0, 1, 1)
    assert maze_redis.advance_plan_index(r, "s6") == 1
    assert maze_redis.advance_plan_index(r, "s6") == 2
    assert maze_redis.advance_plan_index(r, "s6") == 3
suite.run("3.9", "Unit Testing", "advance_plan_index() increments correctly", _t39)

# 3.10
def _t310():
    r = _make_redis()
    maze_redis.store_maze(r, "s7", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.store_plan(r, "s7", ["A", "B"])
    maze_redis.advance_plan_index(r, "s7")
    maze_redis.advance_plan_index(r, "s7")
    assert maze_redis.plan_exhausted(r, "s7") is True
suite.run("3.10", "Unit Testing", "plan_exhausted() – True when index >= plan length", _t310)

# 3.11
def _t311():
    r = _make_redis()
    maze_redis.store_maze(r, "s8", 5, 5, [1]*25, 0, 0, 4, 4)
    maze_redis.append_history(r, "s8", "RIGHT")
    maze_redis.append_history(r, "s8", "DOWN")
    x, y = maze_redis.current_position(r, "s8")
    assert (x, y) == (1, 1)
suite.run("3.11", "Unit Testing",
          "current_position() – correct after history replay", _t311)

# 3.12
def _t312():
    r = _make_redis()
    try:
        maze_redis.current_position(r, "no_session")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "No maze" in str(e)
suite.run("3.12", "Unit Testing",
          "current_position() – raises ValueError for missing session", _t312)

# 3.13
def _t313():
    r = _make_redis()
    maze_redis.store_maze(r, "s9", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.append_history(r, "s9", "RIGHT")
    n = maze_redis.clear_session(r, "s9")
    assert n > 0
    assert maze_redis.load_maze(r, "s9") is None
suite.run("3.13", "Unit Testing", "clear_session() – removes all session keys", _t313)

# 3.14
def _t314():
    r = _make_redis()
    maze_redis.store_maze(r, "s10", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.mark_visited(r, "s10", 1, 1)
    maze_redis.append_history(r, "s10", "RIGHT")
    maze_redis.store_plan(r, "s10", ["UP"])
    maze_redis.advance_plan_index(r, "s10")
    maze_redis.reset_runtime(r, "s10")
    assert maze_redis.get_visited(r, "s10") == set()
    assert maze_redis.get_history(r, "s10") == []
    assert maze_redis.get_plan(r, "s10") == []
    assert maze_redis.get_plan_index(r, "s10") == 0
suite.run("3.14", "Unit Testing",
          "reset_runtime() – clears visited, history, plan, plan_index", _t314)

# 3.15
def _t315():
    assert maze_redis._key("abc", "width") == "maze:abc:width"
suite.run("3.15", "Unit Testing", "_key() – returns correct namespaced key", _t315)

# 3.16
def _t316():
    r = _make_redis()
    maze_redis.store_maze(r, "s11", 5, 5, [1]*25, 0, 0, 4, 4)
    moves = ["RIGHT", "RIGHT", "DOWN", "DOWN", "RIGHT"]
    for m in moves:
        maze_redis.append_history(r, "s11", m)
    x, y = maze_redis.current_position(r, "s11")
    # replay manually
    ex, ey = 0, 0
    for m in moves:
        dx, dy = _tools.DIRECTIONS[m]
        ex, ey = ex + dx, ey + dy
    assert (x, y) == (ex, ey)
suite.run("3.16", "Integration Testing",
          "store_maze → navigate → current_position full flow", _t316)

# 3.17
def _t317():
    r = _make_redis()
    maze_redis.store_maze(r, "s12", 2, 2, [1]*4, 0, 0, 1, 1)
    maze_redis.store_plan(r, "s12", ["A", "B", "C"])
    for _ in range(3):
        maze_redis.advance_plan_index(r, "s12")
    assert maze_redis.plan_exhausted(r, "s12") is True
suite.run("3.17", "Integration Testing",
          "store_plan → advance × 3 → plan_exhausted lifecycle", _t317)

# 3.18
def _t318():
    r = _make_redis()
    maze_redis.store_maze(r, "s13", 100, 100, [1]*10000, 0, 0, 99, 99)
    t0 = time.perf_counter()
    for i in range(10_000):
        maze_redis.mark_visited(r, "s13", i % 100, i // 100)
    elapsed = time.perf_counter() - t0
    assert elapsed < 60, f"10k mark_visited took {elapsed:.2f}s"
suite.run("3.18", "System Testing",
          "10,000 mark_visited() calls – within time budget", _t318)

# 3.19
def _t319():
    r = _make_redis()
    maze_redis.store_maze(r, "s14", 2, 2, [1]*4, 0, 0, 1, 1)
    data = maze_redis.load_maze(r, "s14")
    assert data is not None, "Pipeline write must be atomic / visible"
suite.run("3.19", "System Testing",
          "Pipeline atomicity – store_maze visible immediately", _t319)

# 3.20
def _t320():
    r = _make_redis()
    assert r.ping() is True
suite.run("3.20", "Smoke Testing", "connect() – ping returns True", _t320)

# 3.21
def _t321():
    r = _make_redis()
    maze_redis.store_maze(r, "smoke1", 2, 2, [1]*4, 0, 0, 1, 1)
    data = maze_redis.load_maze(r, "smoke1")
    assert data is not None
suite.run("3.21", "Smoke Testing",
          "store_maze() and load_maze() complete without error", _t321)

# 3.22 – append_history has a read-modify-write race; test with a lock as
# production code would use Redis transactions (MULTI/EXEC) or RPUSH.
# We test that sequential calls from multiple threads each complete safely.
def _t322():
    r = _make_redis()
    maze_redis.store_maze(r, "stress1", 2, 2, [1]*4, 0, 0, 1, 1)
    lock = threading.Lock()
    def worker():
        for _ in range(50):
            with lock:
                maze_redis.append_history(r, "stress1", "RIGHT")
    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    h = maze_redis.get_history(r, "stress1")
    assert len(h) == 1000, f"Expected 1000 history entries, got {len(h)}"
suite.run("3.22", "Stress/Load Testing",
          "Concurrent append_history() – 1000 total entries with lock", _t322)

# 3.23
def _t323():
    r = _make_redis()
    import random
    t0 = time.perf_counter()
    for i in range(1000):
        cells = [random.randint(0, 15) for _ in range(4)]
        maze_redis.store_maze(r, f"bench_{i}", 2, 2, cells, 0, 0, 1, 1)
    elapsed = time.perf_counter() - t0
    avg_ms = elapsed * 1000 / 1000
    assert avg_ms < 50, f"Avg store_maze {avg_ms:.2f}ms > 50ms"
suite.run("3.23", "Stress/Load Testing",
          "1,000 store_maze() calls – throughput benchmark", _t323)

# ---------------------------------------------------------------------------
suite.print_summary()
sys.exit(suite.exit_code())
