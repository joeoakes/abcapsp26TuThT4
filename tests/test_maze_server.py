"""Tests for maze_server.py — FastAPI endpoints."""

import uuid

from fastapi.testclient import TestClient

from src.backend import maze_redis
from src.backend.maze_server import app
from src.backend.tools_maze import WALL_E, WALL_N, WALL_S, WALL_W

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


# ── Dashboard endpoints ──────────────────────────────────────────────

def test_dashboard_html():
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Mission Dashboard" in resp.text


def test_sessions_list():
    resp = client.get("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body
    assert isinstance(body["sessions"], list)


def test_sessions_team4_prefix_only():
    r = maze_redis.connect()
    tid = f"team4-test-{uuid.uuid4().hex[:8]}"
    oid = f"other-{uuid.uuid4().hex[:8]}"
    r.hset(f"mission:{tid}:summary", mapping={"mission_result": "In Progress", "moves_total": "1"})
    r.hset(f"mission:{oid}:summary", mapping={"mission_result": "Success", "moves_total": "2"})
    resp = client.get("/sessions")
    assert resp.status_code == 200
    ids = {s["session_id"] for s in resp.json()["sessions"]}
    assert tid in ids
    assert oid not in ids
    r.delete(f"mission:{tid}:summary", f"mission:{oid}:summary")


def test_mission_not_found():
    resp = client.get("/mission/nonexistent_session")
    assert resp.status_code == 404


def test_mission_found():
    r = maze_redis.connect()
    sid = _sid()
    r.hset(f"mission:{sid}:summary", mapping={
        "robot_id": "test-bot",
        "mission_type": "explore",
        "moves_total": "10",
        "duration_seconds": "42",
        "mission_result": "Success",
    })
    resp = client.get(f"/mission/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["robot_id"] == "test-bot"
    assert body["moves_total"] == "10"
    r.delete(f"mission:{sid}:summary")


def test_post_mission_summary():
    sid = f"team4-test-{uuid.uuid4().hex[:8]}"
    resp = client.post(f"/mission/{sid}/summary", json={
        "robot_id": "keyboard-player",
        "mission_type": "explore",
        "start_time": "1000",
        "end_time": "2000",
        "moves_left_turn": 1,
        "moves_right_turn": 2,
        "moves_straight": 3,
        "moves_reverse": 0,
        "moves_total": 6,
        "distance_traveled": "2.34",
        "duration_seconds": 50,
        "mission_result": "Aborted",
        "abort_reason": "user reset",
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    g = client.get(f"/mission/{sid}")
    assert g.json()["mission_result"] == "Aborted"
    maze_redis.connect().delete(f"mission:{sid}:summary")


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
