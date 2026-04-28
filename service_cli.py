#!/usr/bin/env python3
"""
Interactive service launcher for local AI stack.

Supports starting/stopping:
- redis-server
- https/maze_https_redis (AI mission HTTPS endpoint on 8446)
- ollama serve
- maze_server.py

Usage:
  python service_cli.py
  python service_cli.py --status
  python service_cli.py --start all
  python service_cli.py --start redis,https_redis,maze
  python service_cli.py --stop all
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / ".service_cli_pids.json"
LOG_DIR = ROOT / ".service_cli_logs"
HTTPS_DIR = ROOT / "https"


SERVICE_ORDER = ["redis", "https_redis", "ollama", "maze"]


def _service_cmd(service: str) -> List[str]:
    if service == "redis":
        return ["redis-server"]
    if service == "https_redis":
        return [str(HTTPS_DIR / "maze_https_redis")]
    if service == "ollama":
        return ["ollama", "serve"]
    if service == "maze":
        return [sys.executable, str(ROOT / "maze_server.py")]
    raise ValueError(f"Unknown service: {service}")


def _service_env(service: str) -> Dict[str, str]:
    env = os.environ.copy()
    if service == "maze":
        # Local dev default; can be overridden externally.
        env.setdefault("MTLS_REQUIRE_CLIENT", "0")
    return env


def _load_pids() -> Dict[str, int]:
    if not PID_FILE.exists():
        return {}
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pids(pids: Dict[str, int]) -> None:
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _cleanup_dead(pids: Dict[str, int]) -> Dict[str, int]:
    return {k: v for k, v in pids.items() if _is_running(v)}


def _service_cwd(service: str) -> str:
    if service == "https_redis":
        return str(HTTPS_DIR)
    return str(ROOT)


def _ensure_service_prereqs(service: str) -> bool:
    if service == "https_redis":
        bin_path = HTTPS_DIR / "maze_https_redis"
        if bin_path.exists():
            return True
        src_path = HTTPS_DIR / "maze_https_redis.c"
        if not src_path.exists():
            print(f"[error] Missing {src_path}")
            return False
        print("[info] Building https/maze_https_redis ...")
        cmd = (
            "gcc -O2 -Wall -Wextra -std=c11 maze_https_redis.c -o maze_https_redis "
            "$(pkg-config --cflags --libs libmicrohttpd gnutls)"
        )
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(HTTPS_DIR),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("[error] Failed to build maze_https_redis")
            if result.stderr.strip():
                print(result.stderr.strip())
            return False
        return True
    return True


def start_services(services: List[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pids = _cleanup_dead(_load_pids())

    for service in services:
        if service in pids and _is_running(pids[service]):
            print(f"[skip] {service} already running (pid={pids[service]})")
            continue

        if not _ensure_service_prereqs(service):
            continue

        cmd = _service_cmd(service)
        log_path = LOG_DIR / f"{service}.log"
        log = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=_service_cwd(service),
            env=_service_env(service),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        pids[service] = proc.pid
        print(f"[start] {service} pid={proc.pid} log={log_path}")

    _save_pids(pids)
    if "https_redis" in services or "maze" in services:
        print(
            "\nFor maze_game local demo, set endpoints in the same shell:\n"
            '  export AI_ENDPOINT="https://127.0.0.1:8446/mission"\n'
            '  export LOGGING_ENDPOINT="https://127.0.0.1:8446/mission"\n'
            '  export MINIPUPPER_ENDPOINT="https://127.0.0.1:8446/mission"\n'
            '  export AI_MAZE_ENDPOINT="https://127.0.0.1:8447/maze"\n'
            '  export AI_MISSION_WEB_API="https://127.0.0.1:8447/mission"\n'
        )


def stop_services(services: List[str]) -> None:
    pids = _cleanup_dead(_load_pids())
    changed = False

    for service in services:
        pid = pids.get(service)
        if not pid:
            print(f"[skip] {service} not running")
            continue
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            os.kill(pid, signal.SIGTERM)
        print(f"[stop] {service} pid={pid}")
        pids.pop(service, None)
        changed = True

    if changed:
        _save_pids(pids)


def status_services() -> None:
    pids = _cleanup_dead(_load_pids())
    _save_pids(pids)
    if not pids:
        print("No managed services are running.")
        return
    for service in SERVICE_ORDER:
        pid = pids.get(service)
        health = _health_check(service)
        if pid:
            print(f"{service:<11} RUNNING pid={pid} health={health}")
        else:
            print(f"{service:<11} stopped")


def _tcp_health(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _health_check(service: str) -> str:
    if service == "redis":
        try:
            ping = subprocess.run(
                ["redis-cli", "-h", "127.0.0.1", "-p", "6379", "ping"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if ping.returncode == 0 and "PONG" in ping.stdout:
                return "ok"
            return "unhealthy"
        except Exception:
            return "ok" if _tcp_health("127.0.0.1", 6379) else "down"
    if service == "https_redis":
        return "ok" if _tcp_health("127.0.0.1", 8446) else "down"
    if service == "ollama":
        return "ok" if _tcp_health("127.0.0.1", 11434) else "down"
    if service == "maze":
        return "ok" if _tcp_health("127.0.0.1", 8447) else "down"
    return "unknown"


def parse_services(value: str) -> List[str]:
    if value == "all":
        return SERVICE_ORDER[:]
    services = [v.strip() for v in value.split(",") if v.strip()]
    invalid = [s for s in services if s not in SERVICE_ORDER]
    if invalid:
        raise ValueError(f"Invalid services: {', '.join(invalid)}")
    return services


def interactive_menu() -> None:
    menu = (
        "\nService CLI\n"
        "1) Start ALL (redis + https_redis + ollama + maze_server)\n"
        "2) Start REDIS only\n"
        "3) Start HTTPS REDIS server only (8446)\n"
        "4) Start OLLAMA only\n"
        "5) Start MAZE SERVER only (8447)\n"
        "6) Stop ALL\n"
        "7) Stop REDIS only\n"
        "8) Stop HTTPS REDIS only\n"
        "9) Stop OLLAMA only\n"
        "10) Stop MAZE SERVER only\n"
        "11) Status\n"
        "0) Exit\n"
    )
    while True:
        print(menu)
        choice = input("Select option: ").strip()
        if choice == "1":
            start_services(["redis", "https_redis", "ollama", "maze"])
        elif choice == "2":
            start_services(["redis"])
        elif choice == "3":
            start_services(["https_redis"])
        elif choice == "4":
            start_services(["ollama"])
        elif choice == "5":
            start_services(["maze"])
        elif choice == "6":
            stop_services(["redis", "https_redis", "ollama", "maze"])
        elif choice == "7":
            stop_services(["redis"])
        elif choice == "8":
            stop_services(["https_redis"])
        elif choice == "9":
            stop_services(["ollama"])
        elif choice == "10":
            stop_services(["maze"])
        elif choice == "11":
            status_services()
        elif choice == "0":
            print("Bye.")
            return
        else:
            print("Invalid option.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Service launcher CLI")
    parser.add_argument("--start", type=str, help="Start services: all or comma list")
    parser.add_argument("--stop", type=str, help="Stop services: all or comma list")
    parser.add_argument("--status", action="store_true", help="Show service status")
    args = parser.parse_args()

    try:
        if args.start:
            start_services(parse_services(args.start))
            return
        if args.stop:
            stop_services(parse_services(args.stop))
            return
        if args.status:
            status_services()
            return
        interactive_menu()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
