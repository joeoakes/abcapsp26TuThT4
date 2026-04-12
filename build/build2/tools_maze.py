"""
Maze utility functions for A* pathfinding.

Works with the SDL2 maze's wall-bitmask representation:
    WALL_N = 1, WALL_E = 2, WALL_S = 4, WALL_W = 8

Cells are stored row-major: cells[y * width + x] = wall bitmask for cell (x, y).
Coordinates: x = column (horizontal), y = row (vertical). Origin (0, 0) is top-left.
"""

import heapq
from typing import List, Optional, Tuple

WALL_N = 1
WALL_E = 2
WALL_S = 4
WALL_W = 8

DIRECTIONS = {
    "UP":    ( 0, -1, WALL_N, WALL_S),
    "RIGHT": ( 1,  0, WALL_E, WALL_W),
    "DOWN":  ( 0,  1, WALL_S, WALL_N),
    "LEFT":  (-1,  0, WALL_W, WALL_E),
}


def _cell_walls(width: int, cells: list, x: int, y: int) -> int:
    return cells[y * width + x]


def legal_moves(
    width: int, height: int, cells: list, x: int, y: int
) -> List[str]:
    """Return legal move names from cell (x, y), respecting walls and bounds."""
    if not (0 <= x < width and 0 <= y < height):
        return []

    walls = _cell_walls(width, cells, x, y)
    result = []
    for name, (dx, dy, wall_bit, _) in DIRECTIONS.items():
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height and not (walls & wall_bit):
            result.append(name)
    return result


def validate_plan(
    plan: List[str],
    width: int,
    height: int,
    cells: list,
    start_x: int,
    start_y: int,
) -> Tuple[bool, str]:
    """
    Check that every move in *plan* is a legal direction string that doesn't
    cross a wall or leave the grid.

    Returns (True, "ok") on success, or (False, reason) on first violation.
    """
    valid_names = set(DIRECTIONS.keys())
    x, y = start_x, start_y

    for step, move in enumerate(plan):
        if move not in valid_names:
            return False, f"Step {step}: invalid direction '{move}'"

        dx, dy, wall_bit, _ = DIRECTIONS[move]
        if _cell_walls(width, cells, x, y) & wall_bit:
            return False, f"Step {step}: wall blocks {move} at ({x}, {y})"

        nx, ny = x + dx, y + dy
        if not (0 <= nx < width and 0 <= ny < height):
            return False, (
                f"Step {step}: {move} from ({x}, {y}) "
                f"goes out of bounds to ({nx}, {ny})"
            )
        x, y = nx, ny

    return True, "ok"


def astar(
    width: int,
    height: int,
    cells: list,
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> Optional[List[str]]:
    """
    A* shortest-path search on a wall-bitmask maze.

    Parameters
    ----------
    width, height : grid dimensions
    cells         : row-major flat list of wall bitmasks (len = width * height)
    start         : (x, y) origin
    goal          : (x, y) target

    Returns
    -------
    List of move strings ("UP", "RIGHT", "DOWN", "LEFT") from start to goal,
    or None if no path exists.
    """
    sx, sy = start
    gx, gy = goal

    if start == goal:
        return []

    counter = 0
    h0 = abs(sx - gx) + abs(sy - gy)
    open_set: list = [(h0, counter, sx, sy)]

    gscore = {(sx, sy): 0}
    came_from: dict = {}
    closed: set = set()

    while open_set:
        _f, _, x, y = heapq.heappop(open_set)

        if (x, y) == (gx, gy):
            path: list[str] = []
            cx, cy = gx, gy
            while (cx, cy) != (sx, sy):
                px, py, move = came_from[(cx, cy)]
                path.append(move)
                cx, cy = px, py
            path.reverse()
            return path

        if (x, y) in closed:
            continue
        closed.add((x, y))

        walls = _cell_walls(width, cells, x, y)
        g_current = gscore[(x, y)]

        for name, (dx, dy, wall_bit, _) in DIRECTIONS.items():
            if walls & wall_bit:
                continue
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in closed:
                continue

            tentative_g = g_current + 1
            if tentative_g < gscore.get((nx, ny), float("inf")):
                gscore[(nx, ny)] = tentative_g
                came_from[(nx, ny)] = (x, y, name)
                counter += 1
                f = tentative_g + abs(nx - gx) + abs(ny - gy)
                heapq.heappush(open_set, (f, counter, nx, ny))

    return None
