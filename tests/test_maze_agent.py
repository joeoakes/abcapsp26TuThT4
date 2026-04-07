"""Tests for maze_agent.py — end-to-end agent loop on known mazes."""

import uuid

from src.backend import maze_redis
from src.backend.maze_agent import build_graph, executor, planner, solve_maze
from src.backend.tools_maze import WALL_E, WALL_N, WALL_S, WALL_W


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


def _make_corridor_5x1():
    """Horizontal corridor: 5 cells, open passages between neighbors."""
    w, h = 5, 1
    cells = [
        WALL_N | WALL_S | WALL_W,
        WALL_N | WALL_S,
        WALL_N | WALL_S,
        WALL_N | WALL_S,
        WALL_N | WALL_S | WALL_E,
    ]
    return w, h, cells


def _make_4x4_with_wall():
    """4x4 grid with vertical wall between col 1 and 2 for rows 0-2."""
    w, h = 4, 4
    cells = [0] * (w * h)
    for y in range(h):
        for x in range(w):
            walls = 0
            if y == 0:     walls |= WALL_N
            if y == h - 1: walls |= WALL_S
            if x == 0:     walls |= WALL_W
            if x == w - 1: walls |= WALL_E
            cells[y * w + x] = walls
    for y in range(3):
        cells[y * w + 1] |= WALL_E
        cells[y * w + 2] |= WALL_W
    return w, h, cells


# ── Executor unit tests ──────────────────────────────────────────────

def test_executor_at_goal():
    state = {
        "x": 3, "y": 3, "goal_x": 3, "goal_y": 3,
        "plan": [], "plan_index": 0,
    }
    result = executor(state)
    assert result["action"] == "DONE"
    assert result["need_plan"] is False


def test_executor_no_plan():
    state = {
        "x": 0, "y": 0, "goal_x": 3, "goal_y": 3,
        "plan": [], "plan_index": 0,
    }
    result = executor(state)
    assert result["need_plan"] is True
    assert result["action"] == "NEED_PLAN"


def test_executor_follows_plan():
    state = {
        "x": 0, "y": 0, "goal_x": 2, "goal_y": 0,
        "plan": ["RIGHT", "RIGHT"], "plan_index": 0,
    }
    result = executor(state)
    assert result["action"] == "RIGHT"
    assert result["x"] == 1
    assert result["y"] == 0
    assert result["plan_index"] == 1


# ── Planner unit tests ───────────────────────────────────────────────

def test_planner_produces_astar_plan():
    w, h, cells = _make_corridor_5x1()
    state = {
        "x": 0, "y": 0, "goal_x": 4, "goal_y": 0,
        "width": w, "height": h, "cells": cells,
    }
    result = planner(state)
    assert result["plan"] == ["RIGHT", "RIGHT", "RIGHT", "RIGHT"]
    assert result["plan_index"] == 0
    assert result["need_plan"] is False


def test_planner_no_path():
    cells = [WALL_N | WALL_E | WALL_S | WALL_W] * 2
    state = {
        "x": 0, "y": 0, "goal_x": 1, "goal_y": 0,
        "width": 2, "height": 1, "cells": cells,
    }
    result = planner(state)
    assert result["action"] == "NO_PATH"
    assert result["plan"] == []


# ── Full graph end-to-end ────────────────────────────────────────────

def test_solve_corridor_no_redis():
    w, h, cells = _make_corridor_5x1()
    result = solve_maze(w, h, cells, (0, 0), (4, 0))
    assert result["action"] == "DONE"
    assert result["x"] == 4
    assert result["y"] == 0


def test_solve_open_grid_no_redis():
    cells = _make_open_grid(5, 5)
    result = solve_maze(5, 5, cells, (0, 0), (4, 4))
    assert result["action"] == "DONE"
    assert result["x"] == 4
    assert result["y"] == 4


def test_solve_detour_no_redis():
    w, h, cells = _make_4x4_with_wall()
    result = solve_maze(w, h, cells, (0, 0), (3, 0))
    assert result["action"] == "DONE"
    assert result["x"] == 3
    assert result["y"] == 0


def test_solve_with_redis():
    """Full loop with Redis state tracking."""
    r = maze_redis.connect()
    sid = f"test_agent_{uuid.uuid4().hex[:8]}"

    w, h, cells = _make_corridor_5x1()
    result = solve_maze(w, h, cells, (0, 0), (4, 0), session_id=sid, redis_conn=r)

    assert result["action"] == "DONE"
    assert result["x"] == 4

    history = maze_redis.get_history(r, sid)
    assert history == ["RIGHT", "RIGHT", "RIGHT", "RIGHT"]

    visited = maze_redis.get_visited(r, sid)
    assert (4, 0) in visited

    maze_redis.clear_session(r, sid)


def test_solve_larger_grid_with_redis():
    """10x10 open grid with Redis — verifies state consistency."""
    r = maze_redis.connect()
    sid = f"test_agent_{uuid.uuid4().hex[:8]}"

    cells = _make_open_grid(10, 10)
    result = solve_maze(10, 10, cells, (0, 0), (9, 9), session_id=sid, redis_conn=r)

    assert result["action"] == "DONE"
    assert result["x"] == 9 and result["y"] == 9

    history = maze_redis.get_history(r, sid)
    assert len(history) == 18

    pos = maze_redis.current_position(r, sid)
    assert pos == (9, 9)

    maze_redis.clear_session(r, sid)


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
