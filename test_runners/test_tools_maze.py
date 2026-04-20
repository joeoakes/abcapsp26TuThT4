"""
test_tools_maze.py
Automated test runner for tools_maze.py — covers A* pathfinding, legal-move
enumeration, and plan validation.

These tests were originally written as a pytest-style module at the repository
root; they are migrated here so the master runner picks them up and the old
duplicate can be removed.

Run from the project root:
    python test_runners/test_tools_maze.py
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_framework import TestSuite

from tools_maze import (
    WALL_E, WALL_N, WALL_S, WALL_W,
    astar,
    legal_moves,
    validate_plan,
)


# ── fixtures ─────────────────────────────────────────────────────────
def _make_open_grid(w: int, h: int) -> list:
    """Grid with no interior walls — only boundary walls."""
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


def _make_corridor_3x1() -> tuple:
    """Three-cell horizontal corridor: (0,0) - (1,0) - (2,0)."""
    w, h = 3, 1
    cells = [
        WALL_N | WALL_S | WALL_W,   # open east
        WALL_N | WALL_S,             # open east & west
        WALL_N | WALL_S | WALL_E,    # open west
    ]
    return w, h, cells


def _make_4x4_with_wall() -> tuple:
    """
    4x4 grid with a vertical wall between col1 and col2 at rows 0-2.
    Passage open at row 3.  Start (0,0), Goal (3,0) forces detour.
    """
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


# ── suite ────────────────────────────────────────────────────────────
suite = TestSuite("tools_maze.py")


# 10.1
def _t10_1():
    w, h, cells = _make_corridor_3x1()
    assert legal_moves(w, h, cells, 0, 0) == ["RIGHT"]
    assert sorted(legal_moves(w, h, cells, 1, 0)) == ["LEFT", "RIGHT"]
    assert legal_moves(w, h, cells, 2, 0) == ["LEFT"]
suite.run("10.1", "Unit Testing", "legal_moves() – corridor enforces wall constraints", _t10_1)


# 10.2
def _t10_2():
    cells = _make_open_grid(5, 5)
    assert sorted(legal_moves(5, 5, cells, 0, 0)) == ["DOWN", "RIGHT"]
suite.run("10.2", "Unit Testing", "legal_moves() – open grid corner has 2 moves", _t10_2)


# 10.3
def _t10_3():
    cells = _make_open_grid(5, 5)
    assert sorted(legal_moves(5, 5, cells, 2, 2)) == ["DOWN", "LEFT", "RIGHT", "UP"]
suite.run("10.3", "Unit Testing", "legal_moves() – open grid center has 4 moves", _t10_3)


# 10.4
def _t10_4():
    cells = _make_open_grid(3, 3)
    assert legal_moves(3, 3, cells, -1, 0) == []
    assert legal_moves(3, 3, cells, 3, 3) == []
suite.run("10.4", "Unit Testing", "legal_moves() – out-of-bounds returns empty list", _t10_4)


# 10.5
def _t10_5():
    w, h, cells = _make_corridor_3x1()
    ok, _ = validate_plan(["RIGHT", "RIGHT"], w, h, cells, 0, 0)
    assert ok
suite.run("10.5", "Unit Testing", "validate_plan() – accepts correct plan", _t10_5)


# 10.6
def _t10_6():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["LEFT"], w, h, cells, 0, 0)
    assert not ok
    assert "wall blocks" in msg or "out of bounds" in msg
suite.run("10.6", "Unit Testing", "validate_plan() – rejects wall-blocked move", _t10_6)


# 10.7
def _t10_7():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["DIAGONAL"], w, h, cells, 0, 0)
    assert not ok
    assert "invalid direction" in msg
suite.run("10.7", "Unit Testing", "validate_plan() – rejects unknown direction", _t10_7)


# 10.8
def _t10_8():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["RIGHT", "RIGHT", "RIGHT"], w, h, cells, 0, 0)
    assert not ok
    assert "out of bounds" in msg or "wall blocks" in msg
suite.run("10.8", "Unit Testing", "validate_plan() – rejects out-of-bounds plan", _t10_8)


# 10.9
def _t10_9():
    w, h, cells = _make_corridor_3x1()
    assert astar(w, h, cells, (0, 0), (2, 0)) == ["RIGHT", "RIGHT"]
suite.run("10.9", "Unit Testing", "astar() – corridor returns minimal plan", _t10_9)


# 10.10
def _t10_10():
    w, h, cells = _make_corridor_3x1()
    assert astar(w, h, cells, (1, 0), (1, 0)) == []
suite.run("10.10", "Unit Testing", "astar() – start == goal returns empty plan", _t10_10)


# 10.11
def _t10_11():
    cells = _make_open_grid(5, 5)
    path = astar(5, 5, cells, (0, 0), (4, 4))
    assert path is not None and len(path) == 8
    ok, _ = validate_plan(path, 5, 5, cells, 0, 0)
    assert ok
suite.run("10.11", "Integration Testing",
          "astar() – 5x5 open grid returns optimal length 8", _t10_11)


# 10.12
def _t10_12():
    w, h, cells = _make_4x4_with_wall()
    path = astar(w, h, cells, (0, 0), (3, 0))
    assert path is not None
    ok, msg = validate_plan(path, w, h, cells, 0, 0)
    assert ok, f"Path invalid: {msg}"
    x, y = 0, 0
    for move in path:
        dx, dy = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[move]
        x, y = x + dx, y + dy
    assert (x, y) == (3, 0)
    assert len(path) == 9, f"Optimal detour is 9 moves, got {len(path)}"
suite.run("10.12", "Integration Testing",
          "astar() – 4x4 with wall detours around obstacle (9 moves)", _t10_12)


# 10.13
def _t10_13():
    cells = [WALL_N | WALL_E | WALL_S | WALL_W,
             WALL_N | WALL_E | WALL_S | WALL_W]
    assert astar(2, 1, cells, (0, 0), (1, 0)) is None
suite.run("10.13", "Integration Testing",
          "astar() – fully walled cells return None", _t10_13)


# 10.14
def _t10_14():
    cells = _make_open_grid(10, 10)
    path = astar(10, 10, cells, (0, 0), (9, 9))
    assert path is not None and len(path) == 18
    ok, _ = validate_plan(path, 10, 10, cells, 0, 0)
    assert ok
suite.run("10.14", "System Testing",
          "astar() – 10x10 grid optimal length 18", _t10_14)


# 10.15
def _t10_15():
    cells = _make_open_grid(50, 50)
    path = astar(50, 50, cells, (0, 0), (49, 49))
    assert path is not None and len(path) == 98
suite.run("10.15", "System Testing",
          "astar() – 50x50 grid optimal length 98 (stress)", _t10_15)


# 10.16
def _t10_16():
    import time
    cells = _make_open_grid(100, 100)
    t0 = time.perf_counter()
    path = astar(100, 100, cells, (0, 0), (99, 99))
    elapsed = time.perf_counter() - t0
    assert path is not None and len(path) == 198
    assert elapsed < 2.0, f"astar 100x100 took {elapsed:.2f}s (>2s budget)"
suite.run("10.16", "Stress/Load Testing",
          "astar() – 100x100 grid completes within 2s", _t10_16)


# ---------------------------------------------------------------------------
suite.print_summary()
sys.exit(suite.exit_code())
