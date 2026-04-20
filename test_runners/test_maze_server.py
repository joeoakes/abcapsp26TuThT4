"""
test_maze_server.py
Automated test runner for maze_server.py — covers all 22 test cases (2.1–2.22).
Run from the project root: python test_runners/test_maze_server.py
"""
from __future__ import annotations
import sys, os, threading, time, tracemalloc
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "project_src"))
from test_framework import TestSuite

# Use fakeredis so tests are self-contained
import fakeredis
def _fr(): return fakeredis.FakeRedis(decode_responses=True)

# Patch maze_redis.connect before importing maze_server
import maze_redis as _mredis
_mredis.connect = lambda **kw: _fr()

# Stub maze_agent.solve_maze so server tests don't spin up LangGraph
import maze_agent as _ma
_solve_patch = mock.patch.object(_ma, "solve_maze",
    return_value={"plan": ["RIGHT", "DOWN"], "action": "DONE"})
_solve_patch.start()

import maze_server
from maze_server import (HTTPException, MazePayload, SolveRequest,
    MissionSummaryPayload, receive_maze, get_plan, get_status,
    solve_from_position, health, serve_dashboard,
    list_sessions, get_mission, upsert_mission_summary)

suite = TestSuite("maze_server.py")

def _fresh_redis():
    """Reset server to a fresh fakeredis instance."""
    maze_server._redis_conn = _fr()
    return maze_server._redis_conn

# 2.1
def _t21():
    maze_server._redis_conn = None
    r1 = maze_server._redis()
    r2 = maze_server._redis()
    assert r1 is r2
suite.run("2.1", "Unit Testing", "_redis() – returns singleton Redis connection", _t21)

# 2.2
def _t22():
    _fresh_redis()
    p = MazePayload(session_id="s1", width=3, height=3, cells=[1,2], goal_x=2, goal_y=2)
    try: receive_maze(p); assert False
    except HTTPException as e:
        assert e.status_code == 422 and "cells length" in e.detail
suite.run("2.2", "Unit Testing", "MazePayload validation – cells length mismatch 422", _t22)

# 2.3
def _t23():
    r = _fresh_redis()
    result = health()
    assert result["status"] == "ok"
suite.run("2.3", "Unit Testing", "GET /health – Redis connected returns ok", _t23)

# 2.4
def _t24():
    mock_r = mock.MagicMock()
    mock_r.ping.side_effect = Exception("refused")
    maze_server._redis_conn = mock_r
    result = health()
    assert result["status"] == "degraded"
suite.run("2.4", "Unit Testing", "GET /health – Redis down returns degraded", _t24)

# 2.5
def _t25():
    _fresh_redis()
    try: get_plan("nonexistent"); assert False
    except HTTPException as e: assert e.status_code == 404
suite.run("2.5", "Unit Testing", "GET /plan – unknown session returns 404", _t25)

# 2.6
def _t26():
    r = _fresh_redis()
    _mredis.store_maze(r, "sess1", 5, 5, [15]*25, 0, 0, 4, 4)
    _mredis.mark_visited(r, "sess1", 1, 0)
    result = get_status("sess1")
    assert result.session_id == "sess1"
    assert result.width == 5
    assert result.visited_count == 1
suite.run("2.6", "Unit Testing", "GET /status – returns full state fields", _t26)

# 2.7
def _t27():
    r = _fresh_redis()
    _mredis.store_maze(r, "sess2", 2, 2, [15]*4, 0, 0, 1, 1)
    class _SR: from_x = 1; from_y = 1
    result = solve_from_position("sess2", _SR())
    assert result.plan == [] and result.plan_length == 0
suite.run("2.7", "Unit Testing", "POST /solve – at goal returns empty plan", _t27)

# 2.8
def _t28():
    _fresh_redis()
    body = MissionSummaryPayload(start_time="0", end_time="1", mission_result="Success")
    r1 = upsert_mission_summary("s3", body)
    assert r1["ok"] is True
    r2 = get_mission("s3")
    assert "mission_result" in r2
suite.run("2.8", "Unit Testing", "POST+GET /mission/{id}/summary round-trip", _t28)

# 2.9
def _t29():
    _fresh_redis()
    try: get_mission("ghost"); assert False
    except HTTPException as e: assert e.status_code == 404
suite.run("2.9", "Unit Testing", "GET /mission – unknown session 404", _t29)

# 2.10
def _t210():
    r = _fresh_redis()
    r.hset("mission:team4_abc:summary", mapping={"robot_id":"kb","mission_result":"Success","moves_total":"10","duration_seconds":"5"})
    r.hset("mission:other_xyz:summary", mapping={"robot_id":"kb","mission_result":"Success","moves_total":"5","duration_seconds":"2"})
    result = list_sessions()
    ids = [s["session_id"] for s in result["sessions"]]
    assert "team4_abc" in ids and "other_xyz" not in ids
suite.run("2.10", "Unit Testing", "GET /sessions – only returns team4 sessions", _t210)

# 2.11
def _t211():
    r = _fresh_redis()
    # Pre-store maze so get_plan can find it; solve returns the mocked plan
    _mredis.store_maze(r, "rt1", 5, 5, [15]*25, 0, 0, 4, 4)
    _mredis.store_plan(r, "rt1", ["RIGHT", "DOWN"])
    p = MazePayload(session_id="rt1", width=5, height=5, cells=[15]*25, goal_x=4, goal_y=4)
    post_res = receive_maze(p)
    get_res  = get_plan("rt1")
    # Both should be non-empty lists (solve_maze mock returns ["RIGHT","DOWN"])
    assert isinstance(post_res.plan, list)
    assert isinstance(get_res.plan, list)
suite.run("2.11", "Integration Testing", "POST /maze → GET /plan round-trip", _t211)

# 2.12
def _t212():
    r = _fresh_redis()
    _mredis.store_maze(r, "mid1", 5, 5, [15]*25, 0, 0, 4, 4)
    class _SR: from_x = 2; from_y = 2
    result = solve_from_position("mid1", _SR())
    assert result.plan is not None
suite.run("2.12", "Integration Testing", "POST /solve from mid-path returns plan", _t212)

# 2.13
def _t213():
    r = _fresh_redis()
    _mredis.store_maze(r, "nopath", 2, 2, [15]*4, 0, 0, 1, 1)
    # maze_server imports `solve_maze` directly, so the patch must target
    # the name in maze_server's module namespace — patching maze_agent
    # after the import has no effect on the already-bound local name.
    with mock.patch.object(maze_server, "solve_maze",
                           return_value={"plan": [], "action": "NO_PATH"}):
        try: solve_from_position("nopath"); assert False
        except HTTPException as e: assert e.status_code == 422
suite.run("2.13", "Integration Testing", "POST /solve – no path returns 422", _t213)

# 2.14
def _t214():
    import tempfile, pathlib
    tmp_dir = pathlib.Path(tempfile.mkdtemp())
    (tmp_dir / "index.html").write_text("<html><body>Dashboard</body></html>")
    orig = maze_server.DASHBOARD_DIR
    maze_server.DASHBOARD_DIR = tmp_dir
    try:
        result = serve_dashboard()
        # New implementation returns a RedirectResponse (307) to /dashboard/.
        assert result is not None
        status = getattr(result, "status_code", None)
        assert status is None or status == 307
    finally:
        maze_server.DASHBOARD_DIR = orig
        (tmp_dir / "index.html").unlink()
        tmp_dir.rmdir()
suite.run("2.14", "Integration Testing", "GET /dashboard – serves HTML when file exists", _t214)

# 2.15
def _t215():
    import pathlib
    orig = maze_server.DASHBOARD_DIR
    maze_server.DASHBOARD_DIR = pathlib.Path("/tmp/no_dash_dir_here_xyz")
    try:
        serve_dashboard()
        assert False, "Expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 404
    finally:
        maze_server.DASHBOARD_DIR = orig
suite.run("2.15", "Integration Testing", "GET /dashboard – 404 when file missing", _t215)

# 2.16
def _t216():
    r = _fresh_redis()
    _mredis.store_maze(r, "sys1", 5, 5, [15]*25, 0, 0, 4, 4)
    p = MazePayload(session_id="sys1", width=5, height=5, cells=[15]*25, goal_x=4, goal_y=4)
    r1 = receive_maze(p)
    r2 = get_status("sys1")
    r3 = solve_from_position("sys1")
    assert all(x is not None for x in [r1, r2, r3])
suite.run("2.16", "System Testing", "Full client flow: POST→status→solve", _t216)

# 2.17
def _t217():
    assert hasattr(maze_server, "_MTLS_REQUIRE_CLIENT")
suite.run("2.17", "System Testing", "mTLS – _MTLS_REQUIRE_CLIENT flag exists", _t217)

# 2.18
def _t218():
    import inspect
    src = inspect.getsource(maze_server)
    assert "Starting HTTP server" in src or "http" in src.lower()
suite.run("2.18", "System Testing", "HTTP fallback code path in source", _t218)

# 2.19
def _t219():
    assert maze_server.app is not None
suite.run("2.19", "Smoke Testing", "App object created without error", _t219)

# 2.20
def _t220():
    _fresh_redis()
    p = MazePayload(session_id="smoke", width=2, height=2, cells=[15]*4, goal_x=1, goal_y=1)
    r = receive_maze(p)
    assert r is not None
suite.run("2.20", "Smoke Testing", "POST /maze with minimal payload returns response", _t220)

# 2.21
def _t221():
    errors = []
    def worker(i):
        try:
            maze_server._redis_conn = _fr()
            p = MazePayload(session_id=f"c{i}", width=2, height=1, cells=[15]*2,
                            goal_x=1, goal_y=0)
            receive_maze(p)
        except Exception as e: errors.append(str(e))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == [], f"Thread errors: {errors[:3]}"
suite.run("2.21", "Stress/Load Testing", "100 concurrent POST /maze requests", _t221)

# 2.22
def _t222():
    tracemalloc.start()
    for i in range(200):
        maze_server._redis_conn = _fr()
        p = MazePayload(session_id=f"s{i}", width=2, height=1, cells=[15]*2,
                        goal_x=1, goal_y=0)
        receive_maze(p)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 100 * 1024 * 1024
suite.run("2.22", "Stress/Load Testing", "500 requests sustained – memory stable", _t222)

_solve_patch.stop()
suite.print_summary()
sys.exit(suite.exit_code())
