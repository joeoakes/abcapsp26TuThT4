"""Tests for maze_server.py — FastAPI endpoints."""

import uuid

from fastapi.testclient import TestClient

import maze_redis
from maze_server import app
from tools_maze import WALL_E, WALL_N, WALL_S, WALL_W

client = TestClient(app)
TEST_PREFIX = "srv_test_" + uuid.uuid4().hex[:8]


def _sid():
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


def _make_corridor_5x1():
    return [
        WALL_N | WALL_S | WALL_W,
        WALL_N | WALL_S,
        WALL_N | WALL_S,
        WALL_N | WALL_S,
        WALL_N | WALL_S | WALL_E,
    ]


# ── Health ───────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── POST /maze ───────────────────────────────────────────────────────

def test_post_maze_corridor():
    sid = _sid()
    resp = client.post("/maze", json={
        "session_id": sid,
        "width": 5, "height": 1,
        "cells": _make_corridor_5x1(),
        "start_x": 0, "start_y": 0,
        "goal_x": 4, "goal_y": 0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert body["plan"] == ["RIGHT", "RIGHT", "RIGHT", "RIGHT"]
    assert body["plan_length"] == 4
    assert body["start"] == [0, 0]
    assert body["goal"] == [4, 0]

    maze_redis.clear_session(maze_redis.connect(), sid)


def test_post_maze_open_grid():
    sid = _sid()
    cells = _make_open_grid(5, 5)
    resp = client.post("/maze", json={
        "session_id": sid,
        "width": 5, "height": 5,
        "cells": cells,
        "start_x": 0, "start_y": 0,
        "goal_x": 4, "goal_y": 4,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_length"] == 8

    maze_redis.clear_session(maze_redis.connect(), sid)


def test_post_maze_bad_cells_length():
    resp = client.post("/maze", json={
        "session_id": "bad",
        "width": 5, "height": 5,
        "cells": [0, 0, 0],
        "goal_x": 4, "goal_y": 4,
    })
    assert resp.status_code == 422


# ── GET /maze/{session_id}/plan ──────────────────────────────────────

def test_get_plan():
    sid = _sid()
    client.post("/maze", json={
        "session_id": sid,
        "width": 5, "height": 1,
        "cells": _make_corridor_5x1(),
        "goal_x": 4, "goal_y": 0,
    })

    resp = client.get(f"/maze/{sid}/plan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_length"] == 4

    maze_redis.clear_session(maze_redis.connect(), sid)


def test_get_plan_not_found():
    resp = client.get("/maze/nonexistent_session/plan")
    assert resp.status_code == 404


# ── GET /maze/{session_id}/status ────────────────────────────────────

def test_get_status():
    sid = _sid()
    client.post("/maze", json={
        "session_id": sid,
        "width": 5, "height": 1,
        "cells": _make_corridor_5x1(),
        "goal_x": 4, "goal_y": 0,
    })

    resp = client.get(f"/maze/{sid}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert body["width"] == 5
    assert body["height"] == 1
    assert body["goal"] == [4, 0]
    assert isinstance(body["maze_sig"], str) and len(body["maze_sig"]) == 64

    maze_redis.clear_session(maze_redis.connect(), sid)


def test_get_status_not_found():
    resp = client.get("/maze/nonexistent_session/status")
    assert resp.status_code == 404


# ── POST /maze/{session_id}/solve ────────────────────────────────────

def test_solve_from_current():
    sid = _sid()
    client.post("/maze", json={
        "session_id": sid,
        "width": 5, "height": 1,
        "cells": _make_corridor_5x1(),
        "goal_x": 4, "goal_y": 0,
    })

    resp = client.post(f"/maze/{sid}/solve")
    assert resp.status_code == 200

    maze_redis.clear_session(maze_redis.connect(), sid)


def test_solve_from_custom_position():
    sid = _sid()
    cells = _make_open_grid(5, 5)
    client.post("/maze", json={
        "session_id": sid,
        "width": 5, "height": 5,
        "cells": cells,
        "goal_x": 4, "goal_y": 4,
    })

    resp = client.post(f"/maze/{sid}/solve", json={"from_x": 2, "from_y": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_length"] == 4
    assert body["start"] == [2, 2]

    maze_redis.clear_session(maze_redis.connect(), sid)


def test_solve_not_found():
    resp = client.post("/maze/nonexistent_session/solve")
    assert resp.status_code == 404


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
