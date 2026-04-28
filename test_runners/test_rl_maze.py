"""
test_rl_maze.py
Automated test runner for rl_maze.py.

Run from the project root:
    python test_runners/test_rl_maze.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "project_src"))

from test_framework import TestSuite
import rl_maze


def _open_maze(w: int, h: int):
    cells = [15] * (w * h)
    for y in range(h):
        for x in range(w):
            if x < w - 1:
                cells[y * w + x] &= ~2
                cells[y * w + x + 1] &= ~8
            if y < h - 1:
                cells[y * w + x] &= ~4
                cells[(y + 1) * w + x] &= ~1
    return cells


suite = TestSuite("rl_maze.py")


def _t121():
    planner = rl_maze.QLearningPlanner()
    cells = _open_maze(5, 5)
    expert = planner.fit_with_astar(
        width=5,
        height=5,
        cells=cells,
        start=(0, 0),
        goal=(4, 4),
        episodes=5,
    )
    assert expert is not None
    assert len(expert) > 0


suite.run("12.1", "Unit Testing", "fit_with_astar() returns expert plan", _t121)


def _t122():
    planner = rl_maze.QLearningPlanner()
    cells = _open_maze(6, 6)
    planner.fit_with_astar(6, 6, cells, (0, 0), (5, 5), episodes=20)
    plan = planner.greedy_plan(6, 6, cells, (0, 0), (5, 5))
    assert plan is not None
    assert len(plan) <= 30


suite.run("12.2", "Unit Testing", "greedy_plan() reaches goal in open maze", _t122)


def _t123():
    planner = rl_maze.QLearningPlanner()
    # Fully blocked maze: no path.
    cells = [15] * (4 * 4)
    expert = planner.fit_with_astar(4, 4, cells, (0, 0), (3, 3), episodes=2)
    assert expert is None


suite.run("12.3", "Unit Testing", "fit_with_astar() returns None when no path", _t123)


def _t124():
    planner = rl_maze.QLearningPlanner()
    cells = _open_maze(5, 5)
    planner.fit_with_astar(
        width=5,
        height=5,
        cells=cells,
        start=(0, 0),
        goal=(4, 4),
        episodes=10,
        trajectory_hints=[["RIGHT", "RIGHT", "DOWN", "DOWN"]],
    )
    key = (4, 4, int(cells[0]) & 0xF, 0, 0)
    qvals = planner.q.get(key)
    assert qvals is not None
    assert qvals["RIGHT"] > 0.0


suite.run("12.4", "Unit Testing", "trajectory hints warm-start Q-values", _t124)


def _t125():
    p1 = rl_maze.get_session_planner("s1")
    p2 = rl_maze.get_session_planner("s1")
    p3 = rl_maze.get_session_planner("s2")
    assert p1 is p2
    assert p1 is not p3


suite.run("12.5", "Integration Testing", "session planner cache isolates sessions", _t125)


def _t126():
    planner = rl_maze.QLearningPlanner()
    cells = _open_maze(10, 10)
    planner.fit_with_astar(10, 10, cells, (0, 0), (9, 9), episodes=15)
    plan = planner.greedy_plan(10, 10, cells, (0, 0), (9, 9), max_steps=300)
    assert plan is not None
    assert len(plan) <= 300


suite.run("12.6", "System Testing", "RL policy scales to 10x10 maze", _t126)


suite.print_summary()
sys.exit(suite.exit_code())
