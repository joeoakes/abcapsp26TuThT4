#!/usr/bin/env python3
"""
run_all_tests.py
Master test runner — executes all 12 maze project test suites and prints
a consolidated summary.

Usage:
    python test_runners/run_all_tests.py [--suite <name>]

Examples:
    python test_runners/run_all_tests.py              # run all suites
    python test_runners/run_all_tests.py --suite agent
    python test_runners/run_all_tests.py --suite redis

Available suite names:
    agent, server, redis, rag, sdl2, mongo, https_redis, telemetry,
    dashboard, tools, mtls, rl
"""
from __future__ import annotations

import sys
import os
import subprocess
import time
import argparse

_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SUITES = [
    ("agent",       "test_maze_agent.py",           "maze_agent.py"),
    ("server",      "test_maze_server.py",           "maze_server.py"),
    ("redis",       "test_maze_redis.py",            "maze_redis.py"),
    ("rag",         "test_rag_maze.py",              "rag_maze.py"),
    ("sdl2",        "test_maze_sdl2.py",             "maze_sdl2_final_send.c"),
    ("mongo",       "test_maze_https_mongo.py",      "maze_https_mongo.c"),
    ("https_redis", "test_maze_https_redis.py",      "maze_https_redis.c"),
    ("telemetry",   "test_maze_https_telemetry.py",  "maze_https_telemetry.c"),
    ("dashboard",   "test_dashboard.py",             "dashboard.html"),
    ("tools",       "test_tools_maze.py",            "tools_maze.py"),
    ("mtls",        "test_mtls_regression.py",       "mTLS / security regression"),
    ("rl",          "test_rl_maze.py",               "rl_maze.py"),
]


def run_suite(script: str, source: str) -> dict:
    path = os.path.join(HERE, script)
    print(f"\n{'━'*65}")
    print(f"{_BOLD}▶  Running: {source}{_RESET}")
    print(f"   Script : {script}")
    print(f"{'━'*65}")

    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        capture_output=False,   # let output stream live
    )
    elapsed = time.perf_counter() - t0

    return {
        "source":   source,
        "script":   script,
        "exit":     result.returncode,
        "elapsed":  elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Maze project master test runner")
    parser.add_argument(
        "--suite", metavar="NAME",
        help="Run only the named suite "
             "(agent|server|redis|rag|sdl2|mongo|https_redis|telemetry|dashboard|tools|mtls|rl)"
    )
    args = parser.parse_args()

    selected = SUITES
    if args.suite:
        selected = [s for s in SUITES if s[0] == args.suite]
        if not selected:
            print(f"{_RED}Unknown suite '{args.suite}'.{_RESET}")
            print(f"Valid names: {', '.join(s[0] for s in SUITES)}")
            sys.exit(1)

    overall_t0 = time.perf_counter()
    results = []
    for _, script, source in selected:
        results.append(run_suite(script, source))

    total_elapsed = time.perf_counter() - overall_t0

    # ── Consolidated summary ─────────────────────────────────────────
    print(f"\n\n{'═'*65}")
    print(f"{_BOLD}  MASTER TEST SUMMARY{_RESET}")
    print(f"{'═'*65}")
    print(f"  {'Source File':<35}  {'Status':<10}  {'Time':>8}")
    print(f"  {'-'*35}  {'-'*10}  {'-'*8}")

    passed_suites = failed_suites = 0
    for r in results:
        ok = r["exit"] == 0
        if ok:
            status = f"{_GREEN}PASS{_RESET}"
            passed_suites += 1
        else:
            status = f"{_RED}FAIL{_RESET}"
            failed_suites += 1
        print(f"  {r['source']:<35}  {status:<18}  {r['elapsed']*1000:>6.0f} ms")

    print(f"  {'-'*35}  {'-'*10}  {'-'*8}")
    print(f"  Total: {len(results)} suites  "
          f"{_GREEN}{passed_suites} passed{_RESET}  "
          f"{_RED}{failed_suites} failed{_RESET}  "
          f"({total_elapsed:.2f}s)")
    print(f"{'═'*65}\n")

    sys.exit(0 if failed_suites == 0 else 1)


if __name__ == "__main__":
    main()
