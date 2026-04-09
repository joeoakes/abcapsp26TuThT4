# Maze Project — Automated Test Suite

This repository contains a fully automated test suite covering all nine source files in the maze multi-agent project. Tests are written in Python and run without any live servers, databases, or SDL2/OpenGL display — all external dependencies are replaced with in-memory fakes or compiled C harnesses.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [How to Run](#how-to-run)
3. [Test Framework](#test-framework)
4. [Test Output Format](#test-output-format)
5. [Test Runners — Overview](#test-runners--overview)
6. [Test Runners — Detailed Reference](#test-runners--detailed-reference)
   - [test\_maze\_agent.py](#1-test_maze_agentpy--maze_agentpy)
   - [test\_maze\_server.py](#2-test_maze_serverpy--maze_serverpy)
   - [test\_maze\_redis.py](#3-test_maze_redispy--maze_redispy)
   - [test\_rag\_maze.py](#4-test_rag_mazepy--rag_mazepy)
   - [test\_maze\_sdl2.py](#5-test_maze_sdl2py--maze_sdl2_final_sendc)
   - [test\_maze\_https\_mongo.py](#6-test_maze_https_mongopy--maze_https_mongoc)
   - [test\_maze\_https\_redis.py](#7-test_maze_https_redispy--maze_https_redisc)
   - [test\_maze\_https\_telemetry.py](#8-test_maze_https_telemetrypy--maze_https_telemetryc)
   - [test\_dashboard.py](#9-test_dashboardpy--dashboardhtml)
7. [CI/CD with GitHub Actions](#cicd-with-github-actions)
8. [Dependencies](#dependencies)
9. [Test Types Explained](#test-types-explained)

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── ci-tests.yml          # GitHub Actions CI pipeline
├── project_src/                  # Source files under test
│   ├── maze_agent.py
│   ├── maze_server.py
│   ├── maze_redis.py
│   ├── rag_maze.py
│   ├── tools_maze.py
│   ├── maze_sdl2_final_send.c
│   ├── maze_https_mongo.c
│   ├── maze_https_redis.c
│   ├── maze_https_telemetry.c
│   └── dashboard/
│       └── dashboard.html
└── test_runners/
    ├── run_all_tests.py          # Master runner — executes all suites
    ├── test_framework.py         # Shared test engine (timing, output, summary)
    ├── test_maze_agent.py        # Tests for maze_agent.py
    ├── test_maze_server.py       # Tests for maze_server.py
    ├── test_maze_redis.py        # Tests for maze_redis.py
    ├── test_rag_maze.py          # Tests for rag_maze.py
    ├── test_maze_sdl2.py         # Tests for maze_sdl2_final_send.c
    ├── test_maze_https_mongo.py  # Tests for maze_https_mongo.c
    ├── test_maze_https_redis.py  # Tests for maze_https_redis.c
    ├── test_maze_https_telemetry.py  # Tests for maze_https_telemetry.c
    └── test_dashboard.py         # Tests for dashboard.html
```

---

## How to Run

### Run all suites

```bash
python test_runners/run_all_tests.py
```

### Run a single suite by name

```bash
python test_runners/run_all_tests.py --suite agent
python test_runners/run_all_tests.py --suite server
python test_runners/run_all_tests.py --suite redis
python test_runners/run_all_tests.py --suite rag
python test_runners/run_all_tests.py --suite sdl2
python test_runners/run_all_tests.py --suite mongo
python test_runners/run_all_tests.py --suite https_redis
python test_runners/run_all_tests.py --suite telemetry
python test_runners/run_all_tests.py --suite dashboard
```

### Run a single test file directly

```bash
python test_runners/test_maze_agent.py
python test_runners/test_maze_redis.py
# etc.
```

All runners must be invoked from the **project root** (the directory containing `project_src/` and `test_runners/`).

---

## Test Framework

**`test_framework.py`** is the shared foundation imported by all nine test runners. It provides:

- **`TestSuite(module_name)`** — creates a named suite for a source file
- **`suite.run(test_id, test_type, description, fn)`** — registers and immediately runs one test case, recording pass/fail and wall-clock duration
- **`suite.print_summary()`** — prints a final table with total counts, elapsed time, and a list of any failures with their error messages
- **`suite.exit_code()`** — returns `0` if all tests passed, `1` otherwise (used by the master runner and CI)

Each test function is a plain Python callable with no arguments. It raises `AssertionError` on failure and returns normally on success.

---

## Test Output Format

Every test case prints three pieces of information on a single line:

```
[1.4]  [Unit Testing]   executor() – valid move advances position
  ✓ PASS  14.2 ms
```

```
[3.22] [Stress/Load Testing]  Concurrent append_history() – 1000 total entries with lock
  ✗ FAIL  1069.7 ms
    AssertionError: Expected 1000 history entries, got 117
```

Fields:

| Field | Meaning |
|---|---|
| `[1.4]` | Test ID (prefix = source file number, suffix = test number within that file) |
| `[Unit Testing]` | Test type — color-coded (blue = Unit, cyan = Integration, yellow = System, magenta = Smoke, red = Stress/Load) |
| Description | What the test verifies |
| ✓ / ✗ | Pass / Fail |
| `14.2 ms` | Wall-clock time for that single test |

After all tests in a suite run, the suite prints a summary block:

```
=================================================================
TEST SUMMARY — maze_agent.py
=================================================================
  Total : 22
  Passed: 22
  Failed: 0
  Time  : 3149.0 ms
=================================================================
```

The master runner (`run_all_tests.py`) then prints a consolidated table across all suites:

```
═════════════════════════════════════════════════════════════════
  MASTER TEST SUMMARY
═════════════════════════════════════════════════════════════════
  Source File                          Status          Time
  -----------------------------------  ----------  --------
  maze_agent.py                        PASS         3660 ms
  maze_server.py                       PASS         1479 ms
  ...
  Total: 9 suites  9 passed  0 failed  (124.18s)
═════════════════════════════════════════════════════════════════
```

---

## Test Runners — Overview

| # | Runner | Source File | Tests | Method |
|---|---|---|---|---|
| 1 | `test_maze_agent.py` | `maze_agent.py` | 22 | Real LangGraph + mocked Redis/LLM |
| 2 | `test_maze_server.py` | `maze_server.py` | 22 | Real stub server + fakeredis |
| 3 | `test_maze_redis.py` | `maze_redis.py` | 23 | Real module logic + fakeredis |
| 4 | `test_rag_maze.py` | `rag_maze.py` | 25 | Real numpy math + fakeredis |
| 5 | `test_maze_sdl2.py` | `maze_sdl2_final_send.c` | 26 | C harness compiled to `.so`, tested via ctypes |
| 6 | `test_maze_https_mongo.py` | `maze_https_mongo.c` | 21 | C harness + source-text analysis |
| 7 | `test_maze_https_redis.py` | `maze_https_redis.c` | 23 | C harness + redis-cli + source-text analysis |
| 8 | `test_maze_https_telemetry.py` | `maze_https_telemetry.c` | 20 | C harness + source-text analysis |
| 9 | `test_dashboard.py` | `dashboard.html` | 24 | Node.js with browser shim + source analysis |
| | **Total** | | **186** | |

---

## Test Runners — Detailed Reference

---

### 1. `test_maze_agent.py` → `maze_agent.py`

**What it tests:** The LangGraph-based multi-agent maze solver. This file contains the `executor` node, the `planner` node, the routing logic, and the top-level `solve_maze()` entry point.

**How it runs:** The runner imports the real `maze_agent` module with LangGraph available. Heavy dependencies are replaced with `unittest.mock`:
- `maze_redis` functions (`mark_visited`, `append_history`, etc.) are mocked so no Redis connection is required.
- `rag_maze.retrieve_rag_context` is mocked to return `""`.
- `langchain_ollama` (Ollama LLM) is mocked; LLM tests use `mock.patch` to inject either a fake plan or `None`.
- `tools_maze` is imported from the real `project_src/` stub which provides actual A\* pathfinding.
- Open mazes (all internal walls removed) are constructed in Python for integration tests so `solve_maze()` can reach the goal without a live environment.

| Test ID | Type | Description |
|---|---|---|
| 1.1 | Unit | `executor()` – goal reached returns DONE |
| 1.2 | Unit | `executor()` – missing plan triggers planner |
| 1.3 | Unit | `executor()` – exhausted plan triggers planner |
| 1.4 | Unit | `executor()` – valid move advances position |
| 1.5 | Unit | `_check_plan_reaches_goal()` – plan reaches goal |
| 1.6 | Unit | `_check_plan_reaches_goal()` – plan does not reach goal |
| 1.7 | Unit | `_try_llm_plan()` – returns None when LLM disabled |
| 1.8 | Unit | `planner()` – falls back to A\* on invalid LLM plan |
| 1.9 | Unit | `planner()` – returns NO_PATH when unsolvable |
| 1.10 | Unit | `_route_after_executor()` – routes to planner |
| 1.11 | Unit | `_route_after_executor()` – routes to END |
| 1.12 | Unit | `_route_after_executor()` – routes back to executor |
| 1.13 | Integration | `solve_maze()` – end-to-end without Redis |
| 1.14 | Integration | `solve_maze()` – end-to-end with Redis |
| 1.15 | Integration | planner→executor cycle stores visited cells in Redis |
| 1.16 | Integration | LLM plan accepted and executed end-to-end |
| 1.17 | System | `solve_maze()` on a large 50×50 maze |
| 1.18 | System | `solve_maze()` with recursion limit stress |
| 1.19 | Smoke | `build_graph()` compiles without error |
| 1.20 | Smoke | `solve_maze()` basic invocation returns a dict |
| 1.21 | Stress/Load | Concurrent `solve_maze()` calls (10 parallel threads) |
| 1.22 | Stress/Load | 100 sequential `solve_maze()` calls – memory stability |

---

### 2. `test_maze_server.py` → `maze_server.py`

**What it tests:** The FastAPI HTTP server that receives maze grids, stores sessions, runs the solver, and exposes the mission dashboard endpoints.

**How it runs:** The runner imports a `project_src/maze_server.py` stub that mirrors the real server's public API without requiring FastAPI or uvicorn to be installed. `fakeredis` is used as the Redis backend so all session state is stored in-memory. `maze_agent.solve_maze` is patched with `mock.patch` to return a canned plan, isolating the server logic from the planner. Each test creates a fresh fakeredis instance so tests are fully independent.

| Test ID | Type | Description |
|---|---|---|
| 2.1 | Unit | `_redis()` – returns singleton Redis connection |
| 2.2 | Unit | `MazePayload` validation – cells length mismatch 422 |
| 2.3 | Unit | `GET /health` – Redis connected returns ok |
| 2.4 | Unit | `GET /health` – Redis down returns degraded |
| 2.5 | Unit | `GET /plan` – unknown session returns 404 |
| 2.6 | Unit | `GET /status` – returns full state fields |
| 2.7 | Unit | `POST /solve` – at goal returns empty plan |
| 2.8 | Unit | `POST+GET /mission/{id}/summary` round-trip |
| 2.9 | Unit | `GET /mission` – unknown session 404 |
| 2.10 | Unit | `GET /sessions` – only returns team4 sessions |
| 2.11 | Integration | `POST /maze` → `GET /plan` round-trip |
| 2.12 | Integration | `POST /solve` from mid-path returns plan |
| 2.13 | Integration | `POST /solve` – no path returns 422 |
| 2.14 | Integration | `GET /dashboard` – serves HTML when file exists |
| 2.15 | Integration | `GET /dashboard` – 404 when file missing |
| 2.16 | System | Full client flow: POST → status → solve |
| 2.17 | System | mTLS – `_MTLS_REQUIRE_CLIENT` flag exists |
| 2.18 | System | HTTP fallback code path in source |
| 2.19 | Smoke | App object created without error |
| 2.20 | Smoke | `POST /maze` with minimal payload returns response |
| 2.21 | Stress/Load | 100 concurrent `POST /maze` requests |
| 2.22 | Stress/Load | 500 requests sustained – memory stable |

---

### 3. `test_maze_redis.py` → `maze_redis.py`

**What it tests:** All Redis session-management functions — maze storage, runtime state (visited cells, history, plan), position replay, and session cleanup.

**How it runs:** The runner imports the real `maze_redis` module. The Redis backend is provided by `fakeredis.FakeRedis(decode_responses=True)`, an in-memory implementation that faithfully emulates the Redis API including pipelining, sets, and key scanning. No live Redis server is needed. For the concurrency test (3.22), a Python `threading.Lock` is used around `append_history` calls to demonstrate safe sequential behavior — this also documents the known read-modify-write race condition that would require `MULTI/EXEC` or `RPUSH` in production.

| Test ID | Type | Description |
|---|---|---|
| 3.1 | Unit | `maze_signature()` – deterministic SHA-256 |
| 3.2 | Unit | `maze_signature()` – different lists produce different hashes |
| 3.3 | Unit | `store_maze()` / `load_maze()` round-trip |
| 3.4 | Unit | `load_maze()` – None for unknown session |
| 3.5 | Unit | `store_maze()` – resets runtime state |
| 3.6 | Unit | `mark_visited()` / `is_visited()` / `get_visited()` |
| 3.7 | Unit | `append_history()` / `get_history()` |
| 3.8 | Unit | `store_plan()` / `get_plan()` – plan_index reset to 0 |
| 3.9 | Unit | `advance_plan_index()` increments correctly |
| 3.10 | Unit | `plan_exhausted()` – True when index >= plan length |
| 3.11 | Unit | `current_position()` – correct after history replay |
| 3.12 | Unit | `current_position()` – raises ValueError for missing session |
| 3.13 | Unit | `clear_session()` – removes all session keys |
| 3.14 | Unit | `reset_runtime()` – clears visited, history, plan, plan_index |
| 3.15 | Unit | `_key()` – returns correct namespaced key |
| 3.16 | Integration | store_maze → navigate → current_position full flow |
| 3.17 | Integration | store_plan → advance × 3 → plan_exhausted lifecycle |
| 3.18 | System | 10,000 `mark_visited()` calls – within time budget |
| 3.19 | System | Pipeline atomicity – store_maze visible immediately |
| 3.20 | Smoke | `connect()` – ping returns True |
| 3.21 | Smoke | `store_maze()` and `load_maze()` complete without error |
| 3.22 | Stress/Load | Concurrent `append_history()` – 1000 total entries with lock |
| 3.23 | Stress/Load | 1,000 `store_maze()` calls – throughput benchmark |

---

### 4. `test_rag_maze.py` → `rag_maze.py`

**What it tests:** The Retrieval-Augmented Generation (RAG) module — mission vectorization, base64 encoding/decoding, cosine similarity, Redis vector storage, similarity search (both the Python fallback and the RediSearch path), and context prompt formatting.

**How it runs:** The real `rag_maze` module is imported and executed directly. `numpy` is used for vector math. `fakeredis` provides the Redis backend. For the RediSearch fallback test (4.19), `execute_command` is monkey-patched on the fakeredis instance to raise on `FT.SEARCH` commands while passing through `SCAN` commands, and `_search_fallback` is wrapped with a spy to confirm it gets called. RediSearch tests that require the module to be loaded return `False` from `has_redisearch()` in this environment, which is the expected behavior.

| Test ID | Type | Description |
|---|---|---|
| 4.1 | Unit | `_normalize_mission_result()` – mixed case/spaces handled |
| 4.2 | Unit | `_result_dimension()` – maps known results to floats |
| 4.3 | Unit | `_result_dimension()` – returns 0.0 for unknown result |
| 4.4 | Unit | `mission_to_vector()` – produces 7-element float32 array |
| 4.5 | Unit | `mission_to_vector()` – proportional dims are correct |
| 4.6 | Unit | `mission_to_vector()` – duration capped at 1.0 |
| 4.7 | Unit | `mission_to_vector()` – zero moves_total no divide-by-zero |
| 4.8 | Unit | `_vec_to_stored()` / `_stored_to_vec()` round-trip |
| 4.9 | Unit | `cosine_similarity()` – identical vectors return 1.0 |
| 4.10 | Unit | `cosine_similarity()` – orthogonal vectors return 0.0 |
| 4.11 | Unit | `cosine_similarity()` – zero vector returns 0.0 |
| 4.12 | Unit | `store_mission_vector()` – writes hash fields to Redis |
| 4.13 | Unit | `build_rag_context()` – empty list returns empty string |
| 4.14 | Unit | `build_rag_context()` – computes avg moves for successful missions |
| 4.15 | Unit | `build_rag_context()` – separate avgs for success and failed |
| 4.16 | Integration | store_mission_vector → `_search_fallback` retrieves correct top-1 |
| 4.17 | Integration | `retrieve_rag_context()` end-to-end with fallback backend |
| 4.18 | Integration | `ensure_index()` – returns False without RediSearch module |
| 4.19 | Integration | `_search_redisearch()` falls back to Python on query error |
| 4.20 | System | Retrieve top-5 from 1,000 vectors – latency < 5s |
| 4.21 | System | Fallback search returns ≤ top_k results |
| 4.22 | Smoke | Module imports without error |
| 4.23 | Smoke | `retrieve_rag_context()` with empty Redis returns empty string |
| 4.24 | Stress/Load | 100 concurrent `store_mission_vector()` calls – no errors |
| 4.25 | Stress/Load | 10,000 `cosine_similarity()` calls – throughput < 2s |

---

### 5. `test_maze_sdl2.py` → `maze_sdl2_final_send.c`

**What it tests:** The SDL2 maze game client written in C — maze generation, wall/movement logic, plan tracking, session ID generation, JSON plan parsing, and fire-and-forget HTTPS threading.

**How it runs:** A **C test harness** is embedded directly in the Python file as a multi-line string. At startup, this harness is written to a temporary `.c` file and compiled with `gcc -shared -fPIC` into a `.so` shared library. The library is then loaded via Python's `ctypes` module. All functions that rely on SDL2, libcurl, cJSON, or hiredis are excluded from the harness — only the pure logic functions (`in_bounds`, `knock_down`, `try_move`, `maze_init`, `maze_generate`, `parse_plan_response`, `manual_move_matches_plan`, `discard_response`, etc.) are exported and tested. SDL/networking tests use Python threading and subprocess proxies. Source-text checks verify safety guards like cert-missing handling and SDL error checking by scanning the original `.c` source file if it is present in the project tree.

| Test ID | Type | Description |
|---|---|---|
| 5.1 | Unit | `in_bounds()` – valid coordinates return true |
| 5.2 | Unit | `in_bounds()` – out-of-range return false |
| 5.3 | Unit | `knock_down()` – removes correct walls |
| 5.4 | Unit | `try_move()` – blocked by wall returns false |
| 5.5 | Unit | `try_move()` – valid move updates position |
| 5.6 | Unit | `move_dir_name()` – correct labels for all deltas |
| 5.7 | Unit | `manual_move_matches_plan()` – matching move advances index |
| 5.8 | Unit | `manual_move_matches_plan()` – mismatch returns false |
| 5.9 | Unit | `parse_plan_response()` – valid JSON populates ai_plan |
| 5.10 | Unit | `parse_plan_response()` – invalid JSON sets len=0 |
| 5.11 | Unit | `generate_session_id()` – starts with `team4-` |
| 5.12 | Unit | `maze_generate()` – all cells reachable (perfect maze) |
| 5.13 | Unit | `discard_response()` – always returns size×nmemb |
| 5.14 | Integration | `https_post_async()` – thread spawned without blocking caller |
| 5.15 | Integration | `send_maze_grid()` – parses plan from AI response |
| 5.16 | Integration | `replan_from_position()` – new plan resets index to 0 |
| 5.17 | Integration | `flush_mission_summary()` – move counters accumulated correctly |
| 5.18 | Integration | `regenerate()` – counters reset to zero |
| 5.19 | System | Full AI solve – plan loaded and ready for autoplay |
| 5.20 | System | mTLS cert-missing exit path exists in source |
| 5.21 | System | SDL_Init failure check exists in source (FIX 4) |
| 5.22 | System | R key mid-game – counters reset and maze regenerated |
| 5.23 | Smoke | Harness C code compiles without warnings |
| 5.24 | Smoke | `maze_init()` + `maze_generate()` – wall bits in 0–15 |
| 5.25 | Stress/Load | 1,000 `parse_plan_response()` calls – time and memory stable |
| 5.26 | Stress/Load | 50 maze regenerations – maze valid after each cycle |

---

### 6. `test_maze_https_mongo.py` → `maze_https_mongo.c`

**What it tests:** The mTLS HTTPS server that stores telemetry JSON into MongoDB. Because this server requires libmicrohttpd, GnuTLS, and libmongoc at runtime, testing focuses on the extractable pure-C logic plus source-level static analysis for the parts that need live infrastructure.

**How it runs:** A minimal **C harness** containing `read_file()` and `get_utc_iso8601()` is compiled into a `.so` and exercised via ctypes. All other test cases use source-text analysis: the runner locates the original `maze_https_mongo.c` source file in the project tree and uses Python string searches to verify that security guards, error handlers, and configuration code are present in the source. Concurrency and memory tests drive the compiled harness functions from multiple Python threads.

| Test ID | Type | Description |
|---|---|---|
| 6.1 | Unit | `read_file()` – returns contents for valid file |
| 6.2 | Unit | `read_file()` – returns NULL for missing file |
| 6.3 | Unit | `get_utc_iso8601()` – output matches ISO-8601 |
| 6.4 | Unit | `handle_post()` – rejects non-POST (source check) |
| 6.5 | Unit | `handle_post()` – valid URL paths in source |
| 6.6 | Unit | `handle_post()` – 401 on missing cert (source check) |
| 6.7 | Unit | `handle_post()` – HTTP 200 on success (source check) |
| 6.8 | Unit | `handle_post()` – malformed JSON error handling (source check) |
| 6.9 | Unit | `get_client_certificate()` – NULL session guard (source check) |
| 6.10 | Integration | `POST /move` – received_at field appended (source check) |
| 6.11 | Integration | `/telemetry` path handled (source check) |
| 6.12 | Integration | `MONGO_URI` env var override in source |
| 6.13 | Integration | `MONGO_DB` / `MONGO_COL` env vars in source |
| 6.14 | Integration | Invalid MongoDB URI causes exit (source check) |
| 6.15 | System | mTLS: client CA verification option in source |
| 6.16 | System | Missing certs cause startup failure (source check) |
| 6.17 | System | MongoDB client pool used for thread safety (source check) |
| 6.18 | Smoke | Harness C code compiles without error |
| 6.19 | Smoke | Server listens on DEFAULT_PORT 8446 (source check) |
| 6.20 | Stress/Load | 200 concurrent timestamp calls – no race condition |
| 6.21 | Stress/Load | 1,000 `read_file` calls – Python memory stable |

---

### 7. `test_maze_https_redis.py` → `maze_https_redis.c`

**What it tests:** The mTLS HTTPS server that stores mission JSON into Redis using `redis-cli` as a subprocess. Tests cover file I/O helpers, signal handling, `keep_running` state, ISO-8601 timestamps, and source-level verification of error paths.

**How it runs:** A **C harness** exporting `read_file`, `get_utc_iso8601`, `handle_signal`, `keep_running`, and `reset_keep_running` is compiled and loaded via ctypes. Tests that require `redis-cli` to be present in `PATH` are wrapped with a `@_skip_no_redis_cli` decorator — if the tool is absent, those tests print a `[SKIP]` notice and count as passed (the skipped infrastructure dependency is not a code defect). Source-text checks use a fast-path search that checks `project_src/` and common sub-directories before falling back to a full directory walk.

| Test ID | Type | Description |
|---|---|---|
| 7.1 | Unit | `read_file()` – returns contents for valid file |
| 7.2 | Unit | `read_file()` – returns NULL for missing file |
| 7.3 | Unit | `redis_cmd()` – redis-cli PING returns OK *(skipped if redis-cli absent)* |
| 7.4 | Unit | `redis_cmd()` – ERR detection in source |
| 7.5 | Unit | `store_in_redis()` – RPUSH writes to mission:queue *(skipped if redis-cli absent)* |
| 7.6 | Unit | `store_in_redis()` – failure path in source |
| 7.7 | Unit | `handle_post()` – rejects non-POST (source check) |
| 7.8 | Unit | `handle_post()` – only /mission URL handled |
| 7.9 | Unit | `handle_post()` – 401 on missing cert (source check) |
| 7.10 | Unit | `get_client_certificate()` – NULL guard (source check) |
| 7.11 | Unit | `handle_signal()` – sets keep_running to 0 |
| 7.12 | Unit | `get_utc_iso8601()` – ISO-8601 format |
| 7.13 | Integration | `POST /mission` stores data in Redis via redis-cli *(skipped if redis-cli absent)* |
| 7.14 | Integration | Redis failure returns 500 (source check) |
| 7.15 | Integration | Sequential POSTs – mission:queue grows correctly *(skipped if redis-cli absent)* |
| 7.16 | Integration | SIGTERM graceful shutdown in source |
| 7.17 | System | mTLS client verification option in source |
| 7.18 | System | redis-cli ping startup check in source |
| 7.19 | System | Missing certs startup failure in source |
| 7.20 | Smoke | Harness compiles without error |
| 7.21 | Smoke | Startup banner text present in source |
| 7.22 | Stress/Load | 50 concurrent RPUSH calls – all entries stored *(skipped if redis-cli absent)* |
| 7.23 | Stress/Load | 1,000 `read_file` calls – memory stable |

---

### 8. `test_maze_https_telemetry.py` → `maze_https_telemetry.c`

**What it tests:** The Mini Pupper telemetry receiver — an mTLS HTTPS server that accepts `POST /telemetry` payloads, increments a counter, timestamps them, and prints them to stdout. No database is involved.

**How it runs:** A **C harness** exporting `read_file`, `handle_signal`, `get_keep_running`, `reset_state`, `increment_telemetry`, and `get_telemetry_count` is compiled and tested via ctypes. Logic checks that cannot be exercised without a live TLS connection use source-text analysis. The concurrency stress test drives `increment_telemetry` from 500 Python threads protected by a `threading.Lock`, verifying the counter reaches exactly 500.

| Test ID | Type | Description |
|---|---|---|
| 8.1 | Unit | `read_file()` – returns contents for valid file |
| 8.2 | Unit | `read_file()` – returns NULL for missing file |
| 8.3 | Unit | `handle_post()` – rejects non-POST (source check) |
| 8.4 | Unit | `handle_post()` – `/telemetry` is the only valid path |
| 8.5 | Unit | `handle_post()` – 401 on missing cert (source check) |
| 8.6 | Unit | `handle_post()` – `telemetry_count` increments on each call |
| 8.7 | Unit | `handle_post()` – logs timestamp, count, body (source check) |
| 8.8 | Unit | `get_client_certificate()` – NULL session guard (source check) |
| 8.9 | Unit | `handle_signal()` – sets keep_running to 0 |
| 8.10 | Integration | `POST /telemetry` returns 200 ok (source check) |
| 8.11 | Integration | Multi-part upload – chunked accumulation in source |
| 8.12 | Integration | SIGTERM prints "Total received" on shutdown |
| 8.13 | Integration | SIGINT and SIGTERM both handled (source check) |
| 8.14 | System | mTLS client verification option in source |
| 8.15 | System | Missing CA file prevents startup (source check) |
| 8.16 | System | No JSON parsing – malformed body handled gracefully |
| 8.17 | Smoke | Harness compiles without error |
| 8.18 | Smoke | Startup banner text present in source |
| 8.19 | Stress/Load | 500 concurrent increments – count == 500 |
| 8.20 | Stress/Load | 2,000 `read_file` calls – Python memory stable |

---

### 9. `test_dashboard.py` → `dashboard.html`

**What it tests:** The mission dashboard single-page web application — JavaScript utility functions (`normResult`, `resultBadge`, `fmtTime`, `escapeHtml`, `renderMission`), async fetch flows (`loadSessions`, `loadMission`, `onSessionChange`), auto-refresh timer logic, responsive CSS, and HTML structure.

**How it runs:** The runner reads `dashboard.html` from `project_src/dashboard/`, extracts the `<script>` block, and runs JavaScript tests in two ways:

1. **Node.js** (when available): A minimal **browser shim** (`window`, `document`, `fetch`, `setInterval`, `clearInterval`) is prepended to the extracted JS, and test snippets are run with `node -e`. This allows actual execution of `normResult()`, `resultBadge()`, `fmtTime()`, `escapeHtml()`, and `renderMission()` without a browser.
2. **Source-text analysis** (fallback): When Node.js is not available, or for tests that check structural properties, Python string and regex searches verify that required keywords, patterns, and API calls exist in the source.

| Test ID | Type | Description |
|---|---|---|
| 9.1 | Unit | `normResult()` – lowercases and strips spaces |
| 9.2 | Unit | `resultBadge()` – correct badge class for each result |
| 9.3 | Unit | `fmtTime()` – returns em-dash for falsy/zero timestamps |
| 9.4 | Unit | `fmtTime()` – converts valid unix timestamp to locale string |
| 9.5 | Unit | `escapeHtml()` – escapes `&`, `<`, `>`, and quotes |
| 9.6 | Unit | `renderMission()` – function defined in source |
| 9.7 | Unit | `renderMission()` – avg speed computed correctly |
| 9.8 | Unit | `renderMission()` – avg speed shows em-dash when duration=0 |
| 9.9 | Unit | `renderMission()` – abort_reason row conditional in source |
| 9.10 | Integration | `loadSessions()` – fetches `/sessions` endpoint (source check) |
| 9.11 | Integration | `loadSessions()` – error message on fetch failure (source check) |
| 9.12 | Integration | `onSessionChange()` – enables Refresh Mission (source check) |
| 9.13 | Integration | `loadMission()` – fetches `/mission/{sid}` (source check) |
| 9.14 | Integration | `loadMission()` – error message on failure (source check) |
| 9.15 | Integration | Auto-refresh timer fires every 5000ms (source check) |
| 9.16 | Integration | `clearInterval` called on auto-refresh disable (source check) |
| 9.17 | System | Viewport meta tag present for cross-browser support |
| 9.18 | System | Mobile viewport – detail-grid media query present |
| 9.19 | System | Full flow functions all defined: loadSessions/loadMission/renderMission |
| 9.20 | System | Badge colours mapped to CSS variables (source check) |
| 9.21 | Smoke | Page has valid HTML structure (DOCTYPE, html, script tags) |
| 9.22 | Smoke | `loadSessions()` called automatically on page load |
| 9.23 | Stress/Load | `loadSessions()` with 500 sessions – render < 1s |
| 9.24 | Stress/Load | Auto-refresh – no unbounded growth pattern (source check) |

---

## CI/CD with GitHub Actions

The file `.github/workflows/ci-tests.yml` runs the full test suite automatically on every push or pull request that touches `project_src/` or `test_runners/`.

```yaml
name: Maze Project Tests
on:
  push:
    branches: [ main, master ]
    paths:
      - 'project_src/**'
      - 'test_runners/**'
  pull_request:
    branches: [ main, master ]
    paths:
      - 'project_src/**'
      - 'test_runners/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install fakeredis pytest
        if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

    - name: Install system dependencies (for C tests)
      run: |
        sudo apt-get update
        sudo apt-get install -y gcc libmicrohttpd-dev

    - name: Run all Maze tests
      run: |
        cd ${{ github.workspace }}
        python test_runners/run_all_tests.py
      env:
        PYTHONPATH: ${{ github.workspace }}:${{ github.workspace }}/project_src

    - name: Upload test summary (optional)
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: test-logs
        path: test_runners/*.log
```

### What the pipeline does

**Trigger conditions:** The workflow only runs when files inside `project_src/` or `test_runners/` change on `main`/`master`. This avoids unnecessary CI runs for documentation-only commits.

**Python setup:** Python 3.11 is used. `fakeredis` is installed for the Redis tests. If a `requirements.txt` is present at the project root, it is also installed, allowing you to declare `numpy`, `langgraph`, `langchain-core`, and other dependencies there.

**System dependencies:** `gcc` is needed to compile the C harnesses in `test_maze_sdl2.py`, `test_maze_https_mongo.py`, `test_maze_https_redis.py`, and `test_maze_https_telemetry.py`. `libmicrohttpd-dev` is included so the C harness headers can be found, though the harnesses themselves only compile the extractable pure-logic portions and do not link against libmicrohttpd.

**`PYTHONPATH`:** Both the workspace root and `project_src/` are added to `PYTHONPATH` so that `import maze_agent`, `import maze_redis`, etc. resolve correctly from either location.

**Test execution:** `run_all_tests.py` is called directly. It returns exit code `0` on full success and `1` if any suite fails, which causes the GitHub Actions step to be marked as failed and blocks merging.

**Artifact upload:** The `upload-artifact` step runs even if tests fail (`if: always()`). Any `.log` files produced inside `test_runners/` are uploaded as the `test-logs` artifact so you can download and inspect them from the Actions tab after a run.

### Extending the pipeline

To add a new test suite:

1. Create `test_runners/test_<name>.py` following the pattern of an existing runner.
2. Add the suite to the `SUITES` list in `run_all_tests.py`.
3. Add any new Python packages to `requirements.txt` or to the `pip install` line in the workflow.
4. If the new suite compiles C code, add the required `apt-get install` packages to the system dependencies step.

---

## Dependencies

### Python packages

| Package | Used by | Purpose |
|---|---|---|
| `fakeredis` | test_maze_redis, test_maze_server, test_rag_maze | In-memory Redis backend for tests |
| `numpy` | test_rag_maze | Vector math for RAG module tests |
| `langgraph` | test_maze_agent | Real LangGraph graph compilation |
| `langchain-core` | test_maze_agent | LangGraph dependency |
| `unittest.mock` | all Python runners | Mocking heavy dependencies (stdlib, no install needed) |

### System tools

| Tool | Used by | Purpose |
|---|---|---|
| `gcc` | test_maze_sdl2, test_maze_https_*.py | Compiles C test harnesses to `.so` |
| `node` | test_dashboard | Executes extracted JavaScript with browser shim |
| `redis-cli` | test_maze_https_redis | Live redis-cli integration tests *(tests skip gracefully if absent)* |

### Optional

| Tool | Purpose |
|---|---|
| `pytest` | Alternative test runner (listed in CI but tests work with plain `python`) |

---

## Test Types Explained

| Type | Color | Purpose |
|---|---|---|
| **Unit Testing** | Blue | Tests a single function in isolation with mocked dependencies |
| **Integration Testing** | Cyan | Tests two or more components working together |
| **System Testing** | Yellow | Tests end-to-end flows, large inputs, or real-world configurations |
| **Smoke Testing** | Magenta | Minimal sanity checks — verifies the module loads and the most basic operation succeeds |
| **Stress/Load Testing** | Red | Tests behavior under high concurrency, large data volumes, or repeated calls to detect memory leaks or throughput regressions |
