# Robotics Mission Monorepo

Production-style monorepo for the Mini-Pupper mission stack: backend planning APIs, robot runtime code, vision modules, security infrastructure, and frontend dashboard.

## Top-Level Architecture

```text
src/
  backend/    # Python API + maze intelligence + Redis/RAG modules
  robot/      # C runtime, SDL2 maze engine, telemetry and mission binaries
  vision/     # AprilTag and camera pose modules

frontend/     # Web mission dashboard (index.html + css/js modules)
infra/
  security/   # mTLS servers, cert configs, cert generation scripts
tests/        # Python test suite (test_*.py)
docs/         # Technical docs and wiki pages
```

## Where To Start

- Backend API: `src/backend/maze_server.py`
- Planner graph: `src/backend/maze_agent.py`
- Frontend entrypoint: `frontend/index.html`
- Frontend renderer: `frontend/js/ui-controller.js`
- Security layer: `infra/security/`
- Robot engine: `src/robot/maze/maze_sdl2_final_send.c`

## Run Locally

```bash
pip install -r requirements.txt
make run
```

Then open:

- `https://127.0.0.1:8447/dashboard`

## Tests

```bash
pytest tests -q
```

## Notes

- Theme, telemetry, and HUD update rates are centralized in `frontend/js/ui-controller.js`.
- mTLS cert defaults now live under `infra/security/certs`.
- Additional legacy component notes were consolidated into `docs/wiki/`.
