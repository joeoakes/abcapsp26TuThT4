"""Tests for maze_redis.py — requires a running Redis on localhost:6379."""

import uuid

import maze_redis
from tools_maze import WALL_E, WALL_N, WALL_S, WALL_W

TEST_PREFIX = "test_" + uuid.uuid4().hex[:8]


def _sid():
    """Unique session id so parallel runs don't collide."""
    return f"{TEST_PREFIX}_{uuid.uuid4().hex[:8]}"


def _make_open_grid(w, h):
    cells = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            walls = 0
            if y == 0:     walls |= WALL_N
            if x == w - 1: walls |= WALL_E
            if y == h - 1: walls |= WALL_S
            if x == 0:     walls |= WALL_W
            cells[y * w + x] = walls
    return cells


r = maze_redis.connect()


# ── store / load maze ────────────────────────────────────────────────

def test_store_and_load():
    sid = _sid()
    cells = _make_open_grid(4, 3)
    sig = maze_redis.store_maze(r, sid, 4, 3, cells, 0, 0, 3, 2)

    loaded = maze_redis.load_maze(r, sid)
    assert loaded is not None
    assert loaded["width"] == 4
    assert loaded["height"] == 3
    assert loaded["cells"] == cells
    assert loaded["start_x"] == 0 and loaded["start_y"] == 0
    assert loaded["goal_x"] == 3 and loaded["goal_y"] == 2
    assert loaded["maze_sig"] == sig
    assert len(sig) == 64  # SHA-256 hex

    maze_redis.clear_session(r, sid)


def test_load_missing_session():
    assert maze_redis.load_maze(r, "nonexistent_session_xyz") is None


# ── maze_signature ───────────────────────────────────────────────────

def test_signature_deterministic():
    cells = [15, 14, 13, 12]
    assert maze_redis.maze_signature(cells) == maze_redis.maze_signature(cells)


def test_signature_changes_with_data():
    a = maze_redis.maze_signature([1, 2, 3])
    b = maze_redis.maze_signature([1, 2, 4])
    assert a != b


# ── visited set ──────────────────────────────────────────────────────

def test_visited():
    sid = _sid()
    cells = _make_open_grid(3, 3)
    maze_redis.store_maze(r, sid, 3, 3, cells, 0, 0, 2, 2)

    assert not maze_redis.is_visited(r, sid, 0, 0)
    maze_redis.mark_visited(r, sid, 0, 0)
    assert maze_redis.is_visited(r, sid, 0, 0)

    maze_redis.mark_visited(r, sid, 1, 2)
    visited = maze_redis.get_visited(r, sid)
    assert visited == {(0, 0), (1, 2)}

    maze_redis.clear_session(r, sid)


# ── history ──────────────────────────────────────────────────────────

def test_history():
    sid = _sid()
    cells = _make_open_grid(3, 3)
    maze_redis.store_maze(r, sid, 3, 3, cells, 0, 0, 2, 2)

    assert maze_redis.get_history(r, sid) == []
    maze_redis.append_history(r, sid, "RIGHT")
    maze_redis.append_history(r, sid, "DOWN")
    assert maze_redis.get_history(r, sid) == ["RIGHT", "DOWN"]

    maze_redis.clear_session(r, sid)


# ── plan + plan_index ────────────────────────────────────────────────

def test_plan_lifecycle():
    sid = _sid()
    cells = _make_open_grid(3, 3)
    maze_redis.store_maze(r, sid, 3, 3, cells, 0, 0, 2, 2)

    assert maze_redis.get_plan(r, sid) == []
    assert maze_redis.get_plan_index(r, sid) == 0
    assert maze_redis.plan_exhausted(r, sid)

    plan = ["RIGHT", "RIGHT", "DOWN", "DOWN"]
    maze_redis.store_plan(r, sid, plan)
    assert maze_redis.get_plan(r, sid) == plan
    assert maze_redis.get_plan_index(r, sid) == 0
    assert not maze_redis.plan_exhausted(r, sid)

    maze_redis.advance_plan_index(r, sid)
    assert maze_redis.get_plan_index(r, sid) == 1

    maze_redis.advance_plan_index(r, sid)
    maze_redis.advance_plan_index(r, sid)
    maze_redis.advance_plan_index(r, sid)
    assert maze_redis.get_plan_index(r, sid) == 4
    assert maze_redis.plan_exhausted(r, sid)

    maze_redis.clear_session(r, sid)


# ── reset_runtime ────────────────────────────────────────────────────

def test_reset_runtime():
    sid = _sid()
    cells = _make_open_grid(3, 3)
    maze_redis.store_maze(r, sid, 3, 3, cells, 0, 0, 2, 2)

    maze_redis.mark_visited(r, sid, 1, 1)
    maze_redis.append_history(r, sid, "DOWN")
    maze_redis.store_plan(r, sid, ["UP", "LEFT"])
    maze_redis.advance_plan_index(r, sid)

    maze_redis.reset_runtime(r, sid)

    assert maze_redis.get_visited(r, sid) == set()
    assert maze_redis.get_history(r, sid) == []
    assert maze_redis.get_plan(r, sid) == []
    assert maze_redis.get_plan_index(r, sid) == 0

    maze_redis.clear_session(r, sid)


# ── current_position ─────────────────────────────────────────────────

def test_current_position():
    sid = _sid()
    cells = _make_open_grid(5, 5)
    maze_redis.store_maze(r, sid, 5, 5, cells, 0, 0, 4, 4)

    assert maze_redis.current_position(r, sid) == (0, 0)

    maze_redis.append_history(r, sid, "RIGHT")
    maze_redis.append_history(r, sid, "RIGHT")
    maze_redis.append_history(r, sid, "DOWN")
    assert maze_redis.current_position(r, sid) == (2, 1)

    maze_redis.clear_session(r, sid)


# ── clear_session ────────────────────────────────────────────────────

def test_clear_session():
    sid = _sid()
    cells = _make_open_grid(3, 3)
    maze_redis.store_maze(r, sid, 3, 3, cells, 0, 0, 2, 2)
    maze_redis.mark_visited(r, sid, 0, 0)

    removed = maze_redis.clear_session(r, sid)
    assert removed > 0
    assert maze_redis.load_maze(r, sid) is None


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
            print(f"  ERROR {t.__name__}: {e}")

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
