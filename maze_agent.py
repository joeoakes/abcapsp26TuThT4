"""
Multi-agent maze solver using LangGraph.

Graph cycle:
    executor ──(need_plan?)──> planner ──> executor ──> END

The executor picks the next move from the stored plan.
The planner produces a new plan via A* (and optionally asks an LLM via Ollama).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

import maze_redis
import rag_maze
from tools_maze import astar, validate_plan

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
LLM_ENABLED = bool(OLLAMA_BASE_URL)


# ── Shared state ─────────────────────────────────────────────────────

class MazeState(TypedDict, total=False):
    # Maze grid (set once at start)
    width: int
    height: int
    cells: list
    start_x: int
    start_y: int
    goal_x: int
    goal_y: int
    maze_sig: str

    # Robot position (updated each step)
    x: int
    y: int

    # Plan produced by planner
    plan: List[str]
    plan_index: int
    need_plan: bool

    # Current step result
    action: str       # move direction, "DONE", or "NEED_PLAN"
    reason: str

    # Optional RAG context injected by planner
    rag_context: Optional[str]

    # Session tracking
    session_id: str

    # Redis connection (passed through, not serialized)
    redis: Any


# ── Executor node ────────────────────────────────────────────────────

def executor(state: MazeState) -> dict:
    """
    Pick the next move from the stored plan.
    - If at goal       -> action = "DONE"
    - If plan missing/exhausted -> need_plan = True
    - Otherwise        -> pop next move, advance position
    """
    x, y = state["x"], state["y"]
    gx, gy = state["goal_x"], state["goal_y"]

    if x == gx and y == gy:
        logger.info("Executor: goal reached at (%d, %d)", x, y)
        return {"action": "DONE", "reason": "Goal reached", "need_plan": False}

    plan = state.get("plan", [])
    plan_index = state.get("plan_index", 0)

    if not plan or plan_index >= len(plan):
        logger.info("Executor: no plan available, requesting planner")
        return {
            "action": "NEED_PLAN",
            "reason": "Plan exhausted or missing",
            "need_plan": True,
        }

    move = plan[plan_index]
    from tools_maze import DIRECTIONS
    dx, dy = DIRECTIONS[move][0], DIRECTIONS[move][1]
    nx, ny = x + dx, y + dy

    r = state.get("redis")
    sid = state.get("session_id")
    if r and sid:
        maze_redis.mark_visited(r, sid, nx, ny)
        maze_redis.append_history(r, sid, move)
        maze_redis.advance_plan_index(r, sid)

    logger.info("Executor: move %s from (%d,%d) -> (%d,%d)", move, x, y, nx, ny)

    return {
        "x": nx,
        "y": ny,
        "plan_index": plan_index + 1,
        "action": move,
        "reason": f"Executing step {plan_index}: {move}",
        "need_plan": False,
    }


# ── Planner node ─────────────────────────────────────────────────────

def planner(state: MazeState) -> dict:
    """
    Produce a new plan.
    1. Always try A* first (deterministic, guaranteed optimal).
    2. Optionally ask the LLM for an alternative plan and validate it.
    3. If LLM plan is invalid, fall back to A*.
    """
    x, y = state["x"], state["y"]
    gx, gy = state["goal_x"], state["goal_y"]
    width = state["width"]
    height = state["height"]
    cells = state["cells"]

    astar_plan = astar(width, height, cells, (x, y), (gx, gy))

    if astar_plan is None:
        logger.warning("Planner: A* found no path from (%d,%d) to (%d,%d)", x, y, gx, gy)
        return {
            "plan": [],
            "plan_index": 0,
            "need_plan": False,
            "action": "NO_PATH",
            "reason": "A* found no path to goal",
        }

    chosen_plan = astar_plan
    reason = f"A* plan: {len(astar_plan)} moves"
    rag_context = _fetch_rag_context(state)

    llm_state = {**state}
    if rag_context:
        llm_state["rag_context"] = rag_context

    llm_plan = _try_llm_plan(llm_state)
    if llm_plan is not None:
        ok, msg = validate_plan(llm_plan, width, height, cells, x, y)
        if ok:
            _ends_at_goal = _check_plan_reaches_goal(llm_plan, x, y, gx, gy)
            if _ends_at_goal:
                chosen_plan = llm_plan
                reason = f"LLM plan accepted: {len(llm_plan)} moves"
                logger.info("Planner: LLM plan valid and reaches goal")
            else:
                logger.info("Planner: LLM plan valid but doesn't reach goal, using A*")
        else:
            logger.info("Planner: LLM plan invalid (%s), falling back to A*", msg)

    r = state.get("redis")
    sid = state.get("session_id")
    if r and sid:
        maze_redis.store_plan(r, sid, chosen_plan)

    logger.info("Planner: %s", reason)
    return {
        "plan": chosen_plan,
        "plan_index": 0,
        "need_plan": False,
        "reason": reason,
        "rag_context": rag_context,
    }


def _check_plan_reaches_goal(
    plan: List[str], sx: int, sy: int, gx: int, gy: int
) -> bool:
    from tools_maze import DIRECTIONS
    x, y = sx, sy
    for move in plan:
        dx, dy = DIRECTIONS[move][0], DIRECTIONS[move][1]
        x, y = x + dx, y + dy
    return x == gx and y == gy


def _try_llm_plan(state: MazeState) -> Optional[List[str]]:
    """
    Attempt to get a plan from Ollama. Returns a list of move strings
    or None if the LLM is unavailable or returns unparseable output.

    Only runs when OLLAMA_BASE_URL env var is set (e.g. http://10.170.8.109:11434).
    """
    if not LLM_ENABLED:
        return None

    try:
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            temperature=0,
            timeout=10,
        )

        x, y = state["x"], state["y"]
        gx, gy = state["goal_x"], state["goal_y"]
        width, height = state["width"], state["height"]

        rag_ctx = state.get("rag_context") or ""
        rag_section = f"\nContext from similar mazes:\n{rag_ctx}\n" if rag_ctx else ""

        prompt = (
            f"You are a maze-solving robot. The maze is {width}x{height}.\n"
            f"You are at ({x},{y}). The goal is ({gx},{gy}).\n"
            f"Valid moves: UP (y-1), DOWN (y+1), LEFT (x-1), RIGHT (x+1).\n"
            f"Walls use bitmask: N=1, E=2, S=4, W=8.\n"
            f"{rag_section}"
            f"Return ONLY a JSON array of move strings, e.g. [\"RIGHT\",\"DOWN\"].\n"
            f"No explanation, just the JSON array."
        )

        response = llm.invoke(prompt)
        content = response.content.strip()

        start = content.index("[")
        end = content.rindex("]") + 1
        plan = json.loads(content[start:end])

        valid_dirs = {"UP", "DOWN", "LEFT", "RIGHT"}
        if isinstance(plan, list) and all(m in valid_dirs for m in plan):
            return plan

    except Exception as e:
        logger.debug("LLM plan attempt failed: %s", e)

    return None


def _fetch_rag_context(state: MazeState) -> Optional[str]:
    """Retrieve RAG context from Redis if a connection and maze_sig are available."""
    r = state.get("redis")
    if not r:
        return None

    sid = state.get("session_id", "")
    maze_data = maze_redis.load_maze(r, sid)
    if not maze_data:
        return None

    history = maze_redis.get_history(r, sid)
    left = right = up = down = 0
    for m in history:
        if m == "LEFT":    left += 1
        elif m == "RIGHT": right += 1
        elif m == "UP":    up += 1
        elif m == "DOWN":  down += 1
    total = len(history) or 1

    current_summary = {
        "moves_left_turn":  left,
        "moves_right_turn": right,
        "moves_straight":   up,
        "moves_reverse":    down,
        "moves_total":      len(history),
        "duration_seconds":  0,
        "distance_traveled": total * 0.39,
        "mission_result":   "in_progress",
    }

    try:
        ctx = rag_maze.retrieve_rag_context(r, current_summary, top_k=3)
        if ctx:
            logger.info("Planner: RAG context retrieved (%d chars)", len(ctx))
        return ctx or None
    except Exception as e:
        logger.debug("RAG retrieval failed: %s", e)
        return None


# ── Routing ──────────────────────────────────────────────────────────

def _route_after_executor(state: MazeState) -> str:
    if state.get("need_plan"):
        return "planner"
    if state.get("action") == "DONE":
        return END
    return "executor"


# ── Graph construction ───────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Build and compile the maze-solving agent graph.

        executor ──> (need_plan?) ──> planner ──> executor
                 └──> END (goal reached or no plan needed)
    """
    graph = StateGraph(MazeState)

    graph.add_node("executor", executor)
    graph.add_node("planner", planner)

    graph.set_entry_point("executor")
    graph.add_conditional_edges(
        "executor",
        _route_after_executor,
        {"planner": "planner", "executor": "executor", END: END},
    )
    graph.add_edge("planner", "executor")

    return graph.compile()


# ── Convenience runner ───────────────────────────────────────────────

def solve_maze(
    width: int,
    height: int,
    cells: list,
    start: tuple,
    goal: tuple,
    session_id: str = "default",
    redis_conn=None,
) -> dict:
    """
    Run the full executor/planner loop and return the final state.
    Works with or without Redis (pass redis_conn=None for standalone).
    """
    app = build_graph()

    initial_state: MazeState = {
        "width": width,
        "height": height,
        "cells": cells,
        "start_x": start[0],
        "start_y": start[1],
        "goal_x": goal[0],
        "goal_y": goal[1],
        "x": start[0],
        "y": start[1],
        "plan": [],
        "plan_index": 0,
        "need_plan": False,
        "action": "",
        "reason": "",
        "rag_context": None,
        "session_id": session_id,
        "redis": redis_conn,
    }

    if redis_conn:
        sig = maze_redis.store_maze(
            redis_conn, session_id,
            width, height, cells,
            start[0], start[1], goal[0], goal[1],
        )
        initial_state["maze_sig"] = sig

    final_state = app.invoke(
        initial_state,
        config={"recursion_limit": 500},
    )
    return final_state
