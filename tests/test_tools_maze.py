"""Tests for tools_maze.py — verifies A*, legal_moves, and validate_plan."""

from tools_maze import (
    WALL_E, WALL_N, WALL_S, WALL_W,
    astar,
    legal_moves,
    validate_plan,
)


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
    """
    Simple 3-cell horizontal corridor:
      [0] -- [1] -- [2]
    All surrounded by outer walls, open passages between neighbors.
    """
    w, h = 3, 1
    cells = [
        WALL_N | WALL_S | WALL_W,          # (0,0): open east
        WALL_N | WALL_S,                     # (1,0): open east & west
        WALL_N | WALL_S | WALL_E,           # (2,0): open west
    ]
    return w, h, cells


def _make_4x4_with_wall() -> tuple:
    """
    4x4 grid with a vertical wall between column 1 and column 2
    at rows 0-2 (top three rows), passage open at row 3.

         col0   col1 ‖ col2   col3
    row0  .-------.   ‖   .-------.
    row1  .-------.   ‖   .-------.
    row2  .-------.   ‖   .-------.
    row3  .-------.-------.-------.

    Start (0,0), Goal (3,0).  Must go down to row 3, across, then up.
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


# ── legal_moves ──────────────────────────────────────────────────────

def test_legal_moves_corridor():
    w, h, cells = _make_corridor_3x1()
    assert legal_moves(w, h, cells, 0, 0) == ["RIGHT"]
    assert sorted(legal_moves(w, h, cells, 1, 0)) == ["LEFT", "RIGHT"]
    assert legal_moves(w, h, cells, 2, 0) == ["LEFT"]


def test_legal_moves_open_grid_corner():
    cells = _make_open_grid(5, 5)
    moves = legal_moves(5, 5, cells, 0, 0)
    assert sorted(moves) == ["DOWN", "RIGHT"]


def test_legal_moves_open_grid_center():
    cells = _make_open_grid(5, 5)
    moves = legal_moves(5, 5, cells, 2, 2)
    assert sorted(moves) == ["DOWN", "LEFT", "RIGHT", "UP"]


def test_legal_moves_out_of_bounds():
    cells = _make_open_grid(3, 3)
    assert legal_moves(3, 3, cells, -1, 0) == []
    assert legal_moves(3, 3, cells, 3, 3) == []


# ── validate_plan ────────────────────────────────────────────────────

def test_validate_plan_good():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["RIGHT", "RIGHT"], w, h, cells, 0, 0)
    assert ok, msg


def test_validate_plan_wall_blocked():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["LEFT"], w, h, cells, 0, 0)
    assert not ok
    assert "wall blocks" in msg or "out of bounds" in msg


def test_validate_plan_bad_direction():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["DIAGONAL"], w, h, cells, 0, 0)
    assert not ok
    assert "invalid direction" in msg


def test_validate_plan_out_of_bounds():
    w, h, cells = _make_corridor_3x1()
    ok, msg = validate_plan(["RIGHT", "RIGHT", "RIGHT"], w, h, cells, 0, 0)
    assert not ok
    assert "out of bounds" in msg or "wall blocks" in msg


# ── astar ────────────────────────────────────────────────────────────

def test_astar_corridor():
    w, h, cells = _make_corridor_3x1()
    path = astar(w, h, cells, (0, 0), (2, 0))
    assert path == ["RIGHT", "RIGHT"]


def test_astar_start_equals_goal():
    w, h, cells = _make_corridor_3x1()
    path = astar(w, h, cells, (1, 0), (1, 0))
    assert path == []


def test_astar_open_grid_optimal_length():
    """On an open 5x5 grid, shortest path from (0,0) to (4,4) is 8 moves."""
    cells = _make_open_grid(5, 5)
    path = astar(5, 5, cells, (0, 0), (4, 4))
    assert path is not None
    assert len(path) == 8
    ok, msg = validate_plan(path, 5, 5, cells, 0, 0)
    assert ok, msg


def test_astar_detour_around_wall():
    """A* must find a path around the vertical wall in the 4x4 grid."""
    w, h, cells = _make_4x4_with_wall()
    path = astar(w, h, cells, (0, 0), (3, 0))
    assert path is not None

    ok, msg = validate_plan(path, w, h, cells, 0, 0)
    assert ok, f"Path invalid: {msg}"

    x, y = 0, 0
    for move in path:
        dx, dy = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}[move]
        x, y = x + dx, y + dy
    assert (x, y) == (3, 0), f"Path ended at ({x}, {y}), expected (3, 0)"

    assert len(path) == 9, f"Optimal path is 9 moves, got {len(path)}"


def test_astar_no_path():
    """Fully walled cell with no exits — A* should return None."""
    cells = [WALL_N | WALL_E | WALL_S | WALL_W,
             WALL_N | WALL_E | WALL_S | WALL_W]
    path = astar(2, 1, cells, (0, 0), (1, 0))
    assert path is None


def test_astar_larger_grid():
    """10x10 open grid: optimal from (0,0) to (9,9) is 18 moves."""
    cells = _make_open_grid(10, 10)
    path = astar(10, 10, cells, (0, 0), (9, 9))
    assert path is not None
    assert len(path) == 18
    ok, msg = validate_plan(path, 10, 10, cells, 0, 0)
    assert ok, msg


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
