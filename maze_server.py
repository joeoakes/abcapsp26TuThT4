"""
FastAPI server — receives maze data from the SDL2 client and exposes the
A* / multi-agent solver.

Endpoints:
    POST  /maze                     receive full grid, store, auto-solve, return plan
    GET   /maze/{session_id}/plan   retrieve the current plan for a session
    GET   /maze/{session_id}/status full session state (position, plan, history …)
    POST  /maze/{session_id}/solve  re-solve from current position

Run:
    uvicorn maze_server:app --host 0.0.0.0 --port 8447
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import maze_redis
import rag_maze
from maze_agent import solve_maze
from tools_maze import astar

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

app = FastAPI(title="Maze A* Solver", version="1.0.0")

_redis_conn = None


def _redis():
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = maze_redis.connect(host=REDIS_HOST, port=REDIS_PORT)
    return _redis_conn


# ── Request / response models ────────────────────────────────────────

class MazePayload(BaseModel):
    """JSON body the C maze client sends after generating a maze."""
    session_id: str
    width: int
    height: int
    cells: List[int]
    start_x: int = 0
    start_y: int = 0
    goal_x: int
    goal_y: int


class SolveRequest(BaseModel):
    from_x: Optional[int] = None
    from_y: Optional[int] = None


class PlanResponse(BaseModel):
    session_id: str
    plan: List[str]
    plan_length: int
    start: List[int]
    goal: List[int]


class StatusResponse(BaseModel):
    session_id: str
    width: int
    height: int
    start: List[int]
    goal: List[int]
    current_pos: List[int]
    plan: List[str]
    plan_index: int
    history: List[str]
    visited_count: int
    maze_sig: str


# ── Endpoints ────────────────────────────────────────────────────────

@app.post("/maze", response_model=PlanResponse)
def receive_maze(payload: MazePayload):
    """
    Receive the full maze grid from the C client.
    Stores in Redis, runs the A* agent, returns the plan.
    """
    r = _redis()

    expected = payload.width * payload.height
    if len(payload.cells) != expected:
        raise HTTPException(
            status_code=422,
            detail=f"cells length {len(payload.cells)} != width*height ({expected})",
        )

    result = solve_maze(
        width=payload.width,
        height=payload.height,
        cells=payload.cells,
        start=(payload.start_x, payload.start_y),
        goal=(payload.goal_x, payload.goal_y),
        session_id=payload.session_id,
        redis_conn=r,
    )

    plan = result.get("plan", [])
    return PlanResponse(
        session_id=payload.session_id,
        plan=plan,
        plan_length=len(plan),
        start=[payload.start_x, payload.start_y],
        goal=[payload.goal_x, payload.goal_y],
    )


@app.get("/maze/{session_id}/plan", response_model=PlanResponse)
def get_plan(session_id: str):
    """Return the stored plan for a session."""
    r = _redis()
    maze = maze_redis.load_maze(r, session_id)
    if maze is None:
        raise HTTPException(status_code=404, detail="Session not found")

    plan = maze_redis.get_plan(r, session_id)
    return PlanResponse(
        session_id=session_id,
        plan=plan,
        plan_length=len(plan),
        start=[maze["start_x"], maze["start_y"]],
        goal=[maze["goal_x"], maze["goal_y"]],
    )


@app.get("/maze/{session_id}/status", response_model=StatusResponse)
def get_status(session_id: str):
    """Return full session state."""
    r = _redis()
    maze = maze_redis.load_maze(r, session_id)
    if maze is None:
        raise HTTPException(status_code=404, detail="Session not found")

    pos = maze_redis.current_position(r, session_id)
    plan = maze_redis.get_plan(r, session_id)
    plan_idx = maze_redis.get_plan_index(r, session_id)
    history = maze_redis.get_history(r, session_id)
    visited = maze_redis.get_visited(r, session_id)

    return StatusResponse(
        session_id=session_id,
        width=maze["width"],
        height=maze["height"],
        start=[maze["start_x"], maze["start_y"]],
        goal=[maze["goal_x"], maze["goal_y"]],
        current_pos=list(pos),
        plan=plan,
        plan_index=plan_idx,
        history=history,
        visited_count=len(visited),
        maze_sig=maze["maze_sig"],
    )


@app.post("/maze/{session_id}/solve", response_model=PlanResponse)
def solve_from_position(session_id: str, body: SolveRequest = SolveRequest()):
    """
    Re-solve the maze from a given (or current) position.
    Useful if the robot deviated from the plan.
    """
    r = _redis()
    maze = maze_redis.load_maze(r, session_id)
    if maze is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.from_x is not None and body.from_y is not None:
        sx, sy = body.from_x, body.from_y
    else:
        sx, sy = maze_redis.current_position(r, session_id)

    gx, gy = maze["goal_x"], maze["goal_y"]
    plan = astar(maze["width"], maze["height"], maze["cells"], (sx, sy), (gx, gy))

    if plan is None:
        raise HTTPException(status_code=422, detail="No path found from current position")

    maze_redis.store_plan(r, session_id, plan)

    return PlanResponse(
        session_id=session_id,
        plan=plan,
        plan_length=len(plan),
        start=[sx, sy],
        goal=[gx, gy],
    )


@app.get("/health")
def health():
    """Health check."""
    try:
        _redis().ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        return {"status": "degraded", "redis": str(e)}
