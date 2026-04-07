# Monorepo Migration Guide

## Proposed Professional Structure

```text
abcapsp26TuThT4/
├── src/
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── maze_agent.py
│   │   ├── maze_redis.py
│   │   ├── maze_server.py
│   │   ├── rag_maze.py
│   │   └── tools_maze.py
│   ├── robot/
│   │   ├── maze/
│   │   │   ├── maze_sdl2.c
│   │   │   ├── maze_sdl2_final_send.c
│   │   │   ├── maze_sdl2_json_send.c
│   │   │   └── missions/
│   │   │       ├── Makefile
│   │   │       └── mission_dashboard.c
│   │   ├── telemetry/
│   │   └── http/
│   │       ├── maze_http_mongo.c
│   │       └── maze_http_mongo_alt.c
│   └── vision/
│       └── apriltag/
│           ├── apriltag_pose_cam.py
│           └── apriltag_pose_differentcam.py
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── main.css
│   └── js/
│       ├── api.js
│       ├── theme-engine.js
│       └── ui-controller.js
├── infra/
│   └── security/
│       ├── certs/
│       │   ├── gen_mtls_certs.sh
│       │   ├── server.cnf
│       │   ├── client.cnf
│       │   ├── server.crt
│       │   └── server.key
│       ├── maze_https_mongo.c
│       ├── maze_https_redis.c
│       ├── maze_https_telemetry.c
│       └── maze_https_telemetry
├── tests/
│   ├── test_maze_agent.py
│   ├── test_maze_redis.py
│   ├── test_maze_server.py
│   ├── test_rag_maze.py
│   └── test_tools_maze.py
├── docs/
│   ├── MONOREPO_MIGRATION.md
│   ├── TESTING_GUIDE.md
│   ├── MTLS_DEPLOYMENT.md
│   └── wiki/
├── requirements.txt
├── Makefile
└── run.sh
```

## Migration Table

| From | To |
|---|---|
| `maze_agent.py` | `src/backend/maze_agent.py` |
| `maze_redis.py` | `src/backend/maze_redis.py` |
| `maze_server.py` | `src/backend/maze_server.py` |
| `rag_maze.py` | `src/backend/rag_maze.py` |
| `tools_maze.py` | `src/backend/tools_maze.py` |
| `test_maze_agent.py` | `tests/test_maze_agent.py` |
| `test_maze_redis.py` | `tests/test_maze_redis.py` |
| `test_maze_server.py` | `tests/test_maze_server.py` |
| `test_rag_maze.py` | `tests/test_rag_maze.py` |
| `test_tools_maze.py` | `tests/test_tools_maze.py` |
| `dashboard/*` | `frontend/*` |
| `maze/*` | `src/robot/maze/*` |
| `telemetry/*` | `src/robot/telemetry/*` |
| `http/*` | `src/robot/http/*` |
| `apriltag/*` | `src/vision/apriltag/*` |
| `https/*` | `infra/security/*` |
| `https/certs/*` | `infra/security/certs/*` |
| `data/README.md` | `docs/wiki/data.md` |
| `deployment/README.md` | `docs/wiki/deployment.md` |
| `experiments/README.md` | `docs/wiki/experiments.md` |
| `redis/README.md` | `docs/wiki/redis.md` |
| `vector/README.md` | `docs/wiki/vector.md` |
| `http/README.md` | `docs/wiki/robot-http.md` |
| `telemetry/README.md` | `docs/wiki/robot-telemetry.md` |
| `maze/missions/README.md` | `docs/wiki/robot-missions.md` |
| `apriltag/README.md` | `docs/wiki/vision-apriltag.md` |
| `dashboard/README.md` | `docs/wiki/frontend-dashboard.md` |
| `https/README.md` | `docs/wiki/infra-security-https.md` |
| `https/certs/README.md` | `docs/wiki/infra-security-certs.md` |
| `robot/README.md` | `docs/wiki/robot-legacy.md` |
| `security/README.md` | `docs/wiki/security-legacy.md` |

## Pathing and Runtime Notes

- Python module entrypoint is now:
  - `python -m src.backend.maze_server`
- FastAPI dashboard static mount points to:
  - `frontend/` served on `/dashboard/*`
- mTLS cert defaults now use:
  - `infra/security/certs/server.crt`
  - `infra/security/certs/server.key`
  - `infra/security/certs/ca.crt`
- Frontend API module still calls:
  - `/sessions`
  - `/mission/{session_id}`
  - `/maze/*` endpoints on same origin
