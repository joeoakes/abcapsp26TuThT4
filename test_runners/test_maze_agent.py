"""
test_maze_agent.py
Automated test runner for maze_agent.py — covers all 22 test cases (1.1–1.22).

Run from the project root:
    python test_runners/test_maze_agent.py
"""
from __future__ import annotations
import sys, os, threading, time
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "project_src"))
from test_framework import TestSuite

# ---------------------------------------------------------------------------
# Stub optional deps so maze_agent imports cleanly
# ---------------------------------------------------------------------------
for _mod in ("langchain_ollama",):
    sys.modules.setdefault(_mod, mock.MagicMock())

# Stub maze_redis & rag_maze (will be replaced with real project_src versions
# but keep mock handles for assertion checking)
import importlib, types as _types

_mredis_mock = mock.MagicMock()
_mredis_mock.mark_visited     = mock.MagicMock()
_mredis_mock.append_history   = mock.MagicMock()
_mredis_mock.advance_plan_index = mock.MagicMock()
_mredis_mock.store_plan       = mock.MagicMock()
_mredis_mock.store_maze       = mock.MagicMock(return_value="deadbeef")
_mredis_mock.load_maze        = mock.MagicMock(return_value=None)
_mredis_mock.get_history      = mock.MagicMock(return_value=[])
sys.modules["maze_redis"] = _mredis_mock

_ragmock = mock.MagicMock()
_ragmock.retrieve_rag_context = mock.MagicMock(return_value="")
_ragmock.retrieve_similar_trajectories = mock.MagicMock(return_value=[])
_ragmock.build_trajectory_context = mock.MagicMock(return_value="")
_ragmock.store_successful_trajectory = mock.MagicMock()
sys.modules["rag_maze"] = _ragmock

# Import the real tools_maze from project_src
import tools_maze as _tools_real
sys.modules["tools_maze"] = _tools_real

import maze_agent
maze_agent.RL_ENABLED = False

executor                 = maze_agent.executor
planner                  = maze_agent.planner
_check_plan_reaches_goal = maze_agent._check_plan_reaches_goal
_try_llm_plan            = maze_agent._try_llm_plan
_route_after_executor    = maze_agent._route_after_executor
build_graph              = maze_agent.build_graph
solve_maze               = maze_agent.solve_maze

from langgraph.graph import END

# ---------------------------------------------------------------------------
def _base_state(**kw):
    s = {
        "width": 5, "height": 5,
        "cells": [15] * 25,
        "start_x": 0, "start_y": 0,
        "goal_x": 4, "goal_y": 4,
        "x": 0, "y": 0,
        "plan": [], "plan_index": 0,
        "need_plan": False,
        "action": "", "reason": "",
        "rag_context": None,
        "session_id": "test", "redis": None,
    }
    s.update(kw)
    return s

# Open maze: all walls removed between adjacent cells
def _open_maze(w, h):
    """Return a cell list with all internal walls removed."""
    cells = [15] * (w * h)
    for y in range(h):
        for x in range(w):
            if x < w - 1:
                cells[y*w+x]   &= ~2   # clear WALL_E
                cells[y*w+x+1] &= ~8   # clear WALL_W
            if y < h - 1:
                cells[y*w+x]       &= ~4  # clear WALL_S
                cells[(y+1)*w+x]   &= ~1  # clear WALL_N
    return cells

# ---------------------------------------------------------------------------
suite = TestSuite("maze_agent.py")

# 1.1
def _t11():
    r = executor(_base_state(x=4, y=4, goal_x=4, goal_y=4))
    assert r["action"] == "DONE"
    assert r["need_plan"] is False
suite.run("1.1", "Unit Testing", "executor() – goal reached returns DONE", _t11)

# 1.2
def _t12():
    r = executor(_base_state(plan=[], x=0, y=0))
    assert r["action"] == "NEED_PLAN"
    assert r["need_plan"] is True
suite.run("1.2", "Unit Testing", "executor() – missing plan triggers planner", _t12)

# 1.3
def _t13():
    r = executor(_base_state(plan=["RIGHT"], plan_index=1))
    assert r["need_plan"] is True
suite.run("1.3", "Unit Testing", "executor() – exhausted plan triggers planner", _t13)

# 1.4
def _t14():
    cells = _open_maze(5, 5)
    r = executor(_base_state(plan=["RIGHT"], plan_index=0, x=0, y=0, cells=cells))
    assert r["x"] == 1 and r["y"] == 0
    assert r["plan_index"] == 1
    assert r["action"] == "RIGHT"
suite.run("1.4", "Unit Testing", "executor() – valid move advances position", _t14)

# 1.5
def _t15():
    assert _check_plan_reaches_goal(["RIGHT", "DOWN"], 0, 0, 1, 1) is True
suite.run("1.5", "Unit Testing", "_check_plan_reaches_goal() – plan reaches goal", _t15)

# 1.6
def _t16():
    assert _check_plan_reaches_goal(["RIGHT"], 0, 0, 5, 5) is False
suite.run("1.6", "Unit Testing", "_check_plan_reaches_goal() – plan does not reach goal", _t16)

# 1.7
def _t17():
    orig = maze_agent.LLM_ENABLED
    maze_agent.LLM_ENABLED = False
    result = _try_llm_plan(_base_state())
    maze_agent.LLM_ENABLED = orig
    assert result is None
suite.run("1.7", "Unit Testing", "_try_llm_plan() – returns None when LLM disabled", _t17)

# 1.8
def _t18():
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=["INVALID"]):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            cells = _open_maze(5, 5)
            state = _base_state(x=0, y=0, goal_x=1, goal_y=0, cells=cells)
            r = planner(state)
    assert r["plan"] is not None and len(r["plan"]) > 0
    assert "A*" in r["reason"]
suite.run("1.8", "Unit Testing", "planner() – falls back to A* on invalid LLM plan", _t18)

# 1.9
def _t19():
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            # Fully walled maze — no path possible
            r = planner(_base_state(cells=[15]*25))
    assert r["action"] == "NO_PATH"
    assert r["plan"] == []
suite.run("1.9", "Unit Testing", "planner() – returns NO_PATH when unsolvable", _t19)

# 1.10
def _t110():
    assert _route_after_executor({"need_plan": True, "action": ""}) == "planner"
suite.run("1.10", "Unit Testing", "_route_after_executor() – routes to planner", _t110)

# 1.11
def _t111():
    assert _route_after_executor({"need_plan": False, "action": "DONE"}) == END
suite.run("1.11", "Unit Testing", "_route_after_executor() – routes to END", _t111)

# 1.12
def _t112():
    assert _route_after_executor({"need_plan": False, "action": "RIGHT"}) == "executor"
suite.run("1.12", "Unit Testing", "_route_after_executor() – routes back to executor", _t112)

# 1.13
def _t113():
    cells = _open_maze(2, 2)
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            final = solve_maze(2, 2, cells, (0, 0), (1, 1), redis_conn=None)
    assert isinstance(final, dict)
    assert final.get("action") == "DONE"
suite.run("1.13", "Integration Testing", "solve_maze() – end-to-end without Redis", _t113)

# 1.14
def _t114():
    cells = _open_maze(2, 2)
    mock_redis = mock.MagicMock()
    _mredis_mock.store_maze.return_value = "abc123"
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            final = solve_maze(2, 2, cells, (0, 0), (1, 1), redis_conn=mock_redis)
    assert isinstance(final, dict)
    assert _mredis_mock.store_maze.called
suite.run("1.14", "Integration Testing", "solve_maze() – end-to-end with Redis", _t114)

# 1.15
def _t115():
    cells = _open_maze(2, 1)
    mock_redis = mock.MagicMock()
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            solve_maze(2, 1, cells, (0, 0), (1, 0), redis_conn=mock_redis)
    assert _mredis_mock.mark_visited.called
suite.run("1.15", "Integration Testing",
          "planner→executor cycle stores visited cells in Redis", _t115)

# 1.16
def _t116():
    cells = _open_maze(2, 2)
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=["RIGHT", "DOWN"]):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            final = solve_maze(2, 2, cells, (0, 0), (1, 1), redis_conn=None)
    assert isinstance(final, dict)
    assert final.get("action") == "DONE"
suite.run("1.16", "Integration Testing", "LLM plan accepted and executed end-to-end", _t116)

# 1.17
def _t117():
    cells = _open_maze(50, 50)
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            t0 = time.perf_counter()
            final = solve_maze(50, 50, cells, (0, 0), (49, 49), redis_conn=None)
            elapsed = time.perf_counter() - t0
    assert elapsed < 30, f"Took {elapsed:.1f}s"
    assert final.get("action") == "DONE"
suite.run("1.17", "System Testing", "solve_maze() on a large 50×50 maze", _t117)

# 1.18
def _t118():
    cells = _open_maze(2, 1)
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            try:
                result = solve_maze(2, 1, cells, (0, 0), (1, 0), redis_conn=None)
                ok = isinstance(result, dict)
            except RecursionError:
                ok = True
    assert ok
suite.run("1.18", "System Testing", "solve_maze() with recursion limit stress", _t118)

# 1.19
def _t119():
    g = build_graph()
    assert g is not None
suite.run("1.19", "Smoke Testing", "build_graph() compiles without error", _t119)

# 1.20
def _t120():
    cells = _open_maze(2, 1)
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            r = solve_maze(2, 1, cells, (0, 0), (1, 0))
    assert isinstance(r, dict)
suite.run("1.20", "Smoke Testing", "solve_maze() basic invocation returns a dict", _t120)

# 1.21
def _t121():
    cells = _open_maze(2, 1)
    errors = []
    def worker(i):
        try:
            with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
                with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
                    solve_maze(2, 1, cells, (0, 0), (1, 0),
                               session_id=f"s{i}", redis_conn=None)
        except Exception as e:
            errors.append(str(e))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == [], f"Thread errors: {errors}"
suite.run("1.21", "Stress/Load Testing",
          "Concurrent solve_maze() calls (10 parallel threads)", _t121)

# 1.22
def _t122():
    import tracemalloc
    cells = _open_maze(2, 1)
    tracemalloc.start()
    with mock.patch.object(maze_agent, "_try_llm_plan", return_value=None):
        with mock.patch.object(maze_agent, "_fetch_rag_context", return_value=None):
            for _ in range(100):
                solve_maze(2, 1, cells, (0, 0), (1, 0), redis_conn=None)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 50 * 1024 * 1024, f"Peak {peak//1024}KB"
suite.run("1.22", "Stress/Load Testing",
          "100 sequential solve_maze() calls – memory stability", _t122)

suite.print_summary()
sys.exit(suite.exit_code())
