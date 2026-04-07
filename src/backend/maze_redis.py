"""
Per-session maze state management in Redis.

Key schema (all prefixed with ``maze:{session_id}:``):

  Static (set once when a maze is received):
    width, height          – int
    cells                  – JSON list of wall bitmasks (row-major)
    start_x, start_y       – int
    goal_x, goal_y         – int
    maze_sig               – SHA-256 hex digest of the cell data

  Runtime (updated as the agent navigates):
    visited                – Redis SET of "x,y" strings
    history                – JSON list of move strings already executed
    plan                   – JSON list of planned move strings (from A*)
    plan_index             – int  (next index into *plan* to execute)
"""

import hashlib
import json
from typing import Dict, List, Optional, Tuple

import redis as _redis


def connect(host: str = "127.0.0.1", port: int = 6379, db: int = 0) -> _redis.Redis:
    return _redis.Redis(host=host, port=port, db=db, decode_responses=True)


def _key(session_id: str, suffix: str) -> str:
    return f"maze:{session_id}:{suffix}"


def maze_signature(cells: list) -> str:
    """Deterministic SHA-256 hex digest of the cell list."""
    raw = json.dumps(cells, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


# ── Static state ─────────────────────────────────────────────────────

def store_maze(
    r: _redis.Redis,
    session_id: str,
    width: int,
    height: int,
    cells: list,
    start_x: int,
    start_y: int,
    goal_x: int,
    goal_y: int,
) -> str:
    """
    Persist the maze grid and endpoints.  Returns the computed maze_sig.
    Also resets any runtime state for this session.
    """
    sig = maze_signature(cells)

    pipe = r.pipeline()
    pipe.set(_key(session_id, "width"),   width)
    pipe.set(_key(session_id, "height"),  height)
    pipe.set(_key(session_id, "cells"),   json.dumps(cells))
    pipe.set(_key(session_id, "start_x"), start_x)
    pipe.set(_key(session_id, "start_y"), start_y)
    pipe.set(_key(session_id, "goal_x"),  goal_x)
    pipe.set(_key(session_id, "goal_y"),  goal_y)
    pipe.set(_key(session_id, "maze_sig"), sig)
    pipe.execute()

    reset_runtime(r, session_id)
    return sig


def load_maze(
    r: _redis.Redis, session_id: str
) -> Optional[Dict]:
    """
    Load static maze data.  Returns a dict with keys
    {width, height, cells, start_x, start_y, goal_x, goal_y, maze_sig}
    or None if the session doesn't exist.
    """
    width_raw = r.get(_key(session_id, "width"))
    if width_raw is None:
        return None

    return {
        "width":   int(r.get(_key(session_id, "width"))),
        "height":  int(r.get(_key(session_id, "height"))),
        "cells":   json.loads(r.get(_key(session_id, "cells"))),
        "start_x": int(r.get(_key(session_id, "start_x"))),
        "start_y": int(r.get(_key(session_id, "start_y"))),
        "goal_x":  int(r.get(_key(session_id, "goal_x"))),
        "goal_y":  int(r.get(_key(session_id, "goal_y"))),
        "maze_sig": r.get(_key(session_id, "maze_sig")),
    }


# ── Runtime state ────────────────────────────────────────────────────

def reset_runtime(r: _redis.Redis, session_id: str) -> None:
    """Clear all runtime keys for a session (visited, history, plan, plan_index)."""
    pipe = r.pipeline()
    pipe.delete(_key(session_id, "visited"))
    pipe.set(_key(session_id, "history"),    json.dumps([]))
    pipe.set(_key(session_id, "plan"),       json.dumps([]))
    pipe.set(_key(session_id, "plan_index"), 0)
    pipe.execute()


def mark_visited(r: _redis.Redis, session_id: str, x: int, y: int) -> None:
    r.sadd(_key(session_id, "visited"), f"{x},{y}")


def is_visited(r: _redis.Redis, session_id: str, x: int, y: int) -> bool:
    return r.sismember(_key(session_id, "visited"), f"{x},{y}")


def get_visited(r: _redis.Redis, session_id: str) -> set:
    raw = r.smembers(_key(session_id, "visited"))
    return {tuple(map(int, s.split(","))) for s in raw} if raw else set()


def append_history(r: _redis.Redis, session_id: str, move: str) -> List[str]:
    """Append a move to history and return the updated list."""
    history = get_history(r, session_id)
    history.append(move)
    r.set(_key(session_id, "history"), json.dumps(history))
    return history


def get_history(r: _redis.Redis, session_id: str) -> List[str]:
    raw = r.get(_key(session_id, "history"))
    return json.loads(raw) if raw else []


def store_plan(r: _redis.Redis, session_id: str, plan: List[str]) -> None:
    """Store a new plan and reset plan_index to 0."""
    pipe = r.pipeline()
    pipe.set(_key(session_id, "plan"),       json.dumps(plan))
    pipe.set(_key(session_id, "plan_index"), 0)
    pipe.execute()


def get_plan(r: _redis.Redis, session_id: str) -> List[str]:
    raw = r.get(_key(session_id, "plan"))
    return json.loads(raw) if raw else []


def get_plan_index(r: _redis.Redis, session_id: str) -> int:
    raw = r.get(_key(session_id, "plan_index"))
    return int(raw) if raw else 0


def advance_plan_index(r: _redis.Redis, session_id: str) -> int:
    """Increment plan_index by 1 and return the new value."""
    return r.incr(_key(session_id, "plan_index"))


def plan_exhausted(r: _redis.Redis, session_id: str) -> bool:
    return get_plan_index(r, session_id) >= len(get_plan(r, session_id))


# ── Convenience ──────────────────────────────────────────────────────

def current_position(r: _redis.Redis, session_id: str) -> Tuple[int, int]:
    """
    Derive current (x, y) by replaying history from the start position.
    Returns start position if history is empty.
    """
    from src.backend.tools_maze import DIRECTIONS

    maze = load_maze(r, session_id)
    if maze is None:
        raise ValueError(f"No maze stored for session {session_id}")

    x, y = maze["start_x"], maze["start_y"]
    for move in get_history(r, session_id):
        dx, dy = DIRECTIONS[move][0], DIRECTIONS[move][1]
        x, y = x + dx, y + dy
    return x, y


def clear_session(r: _redis.Redis, session_id: str) -> int:
    """Delete every key for this session. Returns count of keys removed."""
    pattern = _key(session_id, "*")
    keys = list(r.scan_iter(match=pattern))
    if keys:
        return r.delete(*keys)
    return 0
