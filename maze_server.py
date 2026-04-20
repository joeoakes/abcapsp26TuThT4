# FOR LOCAL TESTING WITH NO MTLS
# MTLS_REQUIRE_CLIENT=0 python -m src.backend.maze_server

"""
FastAPI server — receives maze data from the SDL2 client and exposes the
A* / multi-agent solver.

Endpoints:
    POST  /maze                          receive full grid, store, auto-solve, return plan
    GET   /maze/{session_id}/plan        retrieve the current plan for a session
    GET   /maze/{session_id}/status      full session state (position, plan, history …)
    POST  /maze/{session_id}/solve       re-solve from current position
    POST  /mission/{session_id}/summary  upsert mission hash for web dashboard (GameHat)

Run (plain HTTP for local testing):
    uvicorn src.backend.maze_server:app --host 0.0.0.0 --port 8447

Run (mTLS for production — on AI server):
    python -m src.backend.maze_server

Local dashboard in a browser (HTTPS without client cert):
    MTLS_REQUIRE_CLIENT=0 python -m src.backend.maze_server
    Then open https://127.0.0.1:8447/dashboard  (do not use 0.0.0.0 in the URL bar).
"""

from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import maze_redis
from maze_agent import solve_maze

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

REPO_ROOT = Path(__file__).resolve().parents[2]

SSL_CERT = os.getenv("SSL_CERT", str(REPO_ROOT / "infra" / "security" / "certs" / "server.crt"))
SSL_KEY  = os.getenv("SSL_KEY",  str(REPO_ROOT / "infra" / "security" / "certs" / "server.key"))
SSL_CA   = os.getenv("SSL_CA",   str(REPO_ROOT / "infra" / "security" / "certs" / "ca.crt"))
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8447"))
# When false, HTTPS accepts connections without a client cert (local dev / browser only).
_MTLS_REQUIRE_CLIENT = os.getenv("MTLS_REQUIRE_CLIENT", "1").strip().lower() not in (
    "0", "false", "no", "off",
)

app = FastAPI(title="Maze A* Solver", version="1.0.0")

DASHBOARD_DIR = REPO_ROOT / "frontend"
if DASHBOARD_DIR.exists():
    # Serve dashboard static assets and ES modules from /dashboard/*
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

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


class MissionSummaryPayload(BaseModel):
    """Mission hash written by the GameHat client (L, regen, or exit)."""
    robot_id: str = "keyboard-player"
    mission_type: str = "explore"
    start_time: str
    end_time: str
    moves_left_turn: int = 0
    moves_right_turn: int = 0
    moves_straight: int = 0
    moves_reverse: int = 0
    moves_total: int = 0
    distance_traveled: str = "0.00"
    duration_seconds: int = 0
    mission_result: str
    abort_reason: str = ""


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
    Uses the full agent pipeline (LLM-first, A* fallback).
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

    if sx == gx and sy == gy:
        return PlanResponse(
            session_id=session_id,
            plan=[],
            plan_length=0,
            start=[sx, sy],
            goal=[gx, gy],
        )

    result = solve_maze(
        width=maze["width"],
        height=maze["height"],
        cells=maze["cells"],
        start=(sx, sy),
        goal=(gx, gy),
        session_id=session_id,
        redis_conn=r,
    )

    plan = result.get("plan", [])
    if not plan:
        raise HTTPException(status_code=422, detail="No path found from current position")

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


# ── Dashboard endpoints ──────────────────────────────────────────────


@app.get("/dashboard")
def serve_dashboard():
    """Route /dashboard to /dashboard/ so StaticFiles serves index.html."""
    if not DASHBOARD_DIR.exists():
        raise HTTPException(status_code=404, detail="dashboard directory not found")
    return RedirectResponse(url="/dashboard/", status_code=307)


@app.get("/sessions")
def list_sessions():
    """Return mission summaries for sessions whose id starts with ``team4``."""
    r = _redis()
    sessions: List[Dict[str, Any]] = []
    for key in r.scan_iter(match="mission:*:summary"):
        sid = key.split(":")[1]
        if not sid.startswith("team4"):
            continue
        data = r.hgetall(f"mission:{sid}:summary")
        sessions.append({
            "session_id": sid,
            "robot_id": data.get("robot_id", ""),
            "mission_result": data.get("mission_result", ""),
            "moves_total": int(data.get("moves_total", 0)),
            "duration_seconds": int(data.get("duration_seconds", 0)),
        })
    sessions.sort(key=lambda s: s["session_id"], reverse=True)
    return {"sessions": sessions}


@app.get("/mission/{session_id}")
def get_mission(session_id: str):
    """Return the mission summary hash from Redis."""
    r = _redis()
    key = f"mission:{session_id}:summary"
    data = r.hgetall(key)
    if not data:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"session_id": session_id, **data}


@app.post("/mission/{session_id}/summary")
def upsert_mission_summary(session_id: str, body: MissionSummaryPayload):
    """Store mission summary on the AI server Redis (web dashboard reads this)."""
    r = _redis()
    key = f"mission:{session_id}:summary"
    flat = body.model_dump()
    r.hset(key, mapping={k: str(v) for k, v in flat.items()})
    return {"ok": True, "session_id": session_id}


if __name__ == "__main__":
    import uvicorn

    use_ssl = all(os.path.exists(p) for p in (SSL_CERT, SSL_KEY, SSL_CA))

    if use_ssl:
        # CERT_OPTIONAL still *requests* a client cert and triggers browser picker;
        # CERT_NONE does not request one (HTTPS only, for browsers / local dev).
        cert_req = ssl.CERT_REQUIRED if _MTLS_REQUIRE_CLIENT else ssl.CERT_NONE
        print(f"Starting mTLS server on port {LISTEN_PORT}")
        print(f"  cert: {SSL_CERT}  key: {SSL_KEY}  ca: {SSL_CA}")
        print(
            f"  client cert: {'REQUIRED' if _MTLS_REQUIRE_CLIENT else 'not requested (MTLS_REQUIRE_CLIENT=0; use https://127.0.0.1:{LISTEN_PORT}/dashboard)'}"
        )
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=LISTEN_PORT,
            ssl_certfile=SSL_CERT,
            ssl_keyfile=SSL_KEY,
            ssl_ca_certs=SSL_CA,
            ssl_cert_reqs=cert_req,
        )
    else:
        print(f"Starting HTTP server on port {LISTEN_PORT} (no certs found)")
        uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
