#!/usr/bin/env python3
"""
Benchmark RL (A*-shaped Q-learning) versus pure A* on randomized mazes.

Usage:
  # Single benchmark
  ./.venv/bin/python experiments/benchmark_rl_astar.py --episodes 100

  # Multiple scenarios + multiple seeds (writes JSON/CSV)
  ./.venv/bin/python experiments/benchmark_rl_astar.py \
      --multi \
      --sizes 10x8,15x11,21x15 \
      --seeds 42,43,44 \
      --episodes 100 \
      --out experiments/results/rl_astar_multi.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from statistics import mean
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "project_src"))

from rl_maze import QLearningPlanner
from tools_maze import astar

WALL_N = 1
WALL_E = 2
WALL_S = 4
WALL_W = 8


@dataclass
class BenchResult:
    episodes: int
    width: int
    height: int
    astar_success_rate: float
    rl_success_rate: float
    astar_avg_steps: float
    rl_avg_steps: float
    rl_vs_astar_step_ratio: float
    astar_plan_ms_avg: float
    rl_plan_ms_avg: float


def _in_bounds(x: int, y: int, w: int, h: int) -> bool:
    return 0 <= x < w and 0 <= y < h


def _knock(cells: List[int], w: int, x: int, y: int, nx: int, ny: int) -> None:
    i = y * w + x
    j = ny * w + nx
    if nx == x and ny == y - 1:
        cells[i] &= ~WALL_N
        cells[j] &= ~WALL_S
    elif nx == x + 1 and ny == y:
        cells[i] &= ~WALL_E
        cells[j] &= ~WALL_W
    elif nx == x and ny == y + 1:
        cells[i] &= ~WALL_S
        cells[j] &= ~WALL_N
    elif nx == x - 1 and ny == y:
        cells[i] &= ~WALL_W
        cells[j] &= ~WALL_E


def generate_random_maze(w: int, h: int, seed: int) -> List[int]:
    rng = random.Random(seed)
    cells = [WALL_N | WALL_E | WALL_S | WALL_W for _ in range(w * h)]
    visited = [[False for _ in range(w)] for _ in range(h)]
    stack: List[Tuple[int, int]] = [(0, 0)]
    visited[0][0] = True

    while stack:
        x, y = stack[-1]
        neighbors = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if _in_bounds(nx, ny, w, h) and not visited[ny][nx]:
                neighbors.append((nx, ny))
        if not neighbors:
            stack.pop()
            continue
        nx, ny = rng.choice(neighbors)
        _knock(cells, w, x, y, nx, ny)
        visited[ny][nx] = True
        stack.append((nx, ny))

    return cells


def run_benchmark(episodes: int, width: int, height: int, seed: int) -> BenchResult:
    astar_steps = []
    rl_steps = []
    astar_ms = []
    rl_ms = []
    astar_success = 0
    rl_success = 0

    for ep in range(episodes):
        cells = generate_random_maze(width, height, seed + ep)
        start, goal = (0, 0), (width - 1, height - 1)

        t0 = time.perf_counter()
        a_plan = astar(width, height, cells, start, goal)
        astar_ms.append((time.perf_counter() - t0) * 1000.0)
        if a_plan is not None:
            astar_success += 1
            astar_steps.append(len(a_plan))

        planner = QLearningPlanner()
        t1 = time.perf_counter()
        expert = planner.fit_with_astar(width, height, cells, start, goal, episodes=20)
        r_plan = planner.greedy_plan(width, height, cells, start, goal, max_steps=3000)
        if r_plan is None:
            r_plan = expert
        rl_ms.append((time.perf_counter() - t1) * 1000.0)
        if r_plan is not None:
            rl_success += 1
            rl_steps.append(len(r_plan))

    astar_avg_steps = sum(astar_steps) / max(1, len(astar_steps))
    rl_avg_steps = sum(rl_steps) / max(1, len(rl_steps))
    ratio = rl_avg_steps / max(1e-9, astar_avg_steps)

    return BenchResult(
        episodes=episodes,
        width=width,
        height=height,
        astar_success_rate=astar_success / max(1, episodes),
        rl_success_rate=rl_success / max(1, episodes),
        astar_avg_steps=astar_avg_steps,
        rl_avg_steps=rl_avg_steps,
        rl_vs_astar_step_ratio=ratio,
        astar_plan_ms_avg=sum(astar_ms) / max(1, len(astar_ms)),
        rl_plan_ms_avg=sum(rl_ms) / max(1, len(rl_ms)),
    )


def _parse_sizes(raw: str) -> List[Tuple[int, int]]:
    items = []
    for chunk in raw.split(","):
        chunk = chunk.strip().lower()
        if not chunk:
            continue
        if "x" not in chunk:
            raise ValueError(f"Invalid size '{chunk}'. Use WIDTHxHEIGHT (example 21x15).")
        w_s, h_s = chunk.split("x", 1)
        items.append((int(w_s), int(h_s)))
    if not items:
        raise ValueError("At least one size is required.")
    return items


def _parse_seeds(raw: str) -> List[int]:
    seeds = [int(s.strip()) for s in raw.split(",") if s.strip()]
    if not seeds:
        raise ValueError("At least one seed is required.")
    return seeds


def _write_csv(rows: List[Dict], path: str) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run_multi_benchmark(
    episodes: int,
    sizes: List[Tuple[int, int]],
    seeds: List[int],
) -> Dict:
    rows: List[Dict] = []

    for (w, h) in sizes:
        for seed in seeds:
            result = run_benchmark(episodes=episodes, width=w, height=h, seed=seed)
            rows.append(
                {
                    "width": w,
                    "height": h,
                    "seed": seed,
                    "episodes": episodes,
                    "astar_success_rate": result.astar_success_rate,
                    "rl_success_rate": result.rl_success_rate,
                    "astar_avg_steps": result.astar_avg_steps,
                    "rl_avg_steps": result.rl_avg_steps,
                    "rl_vs_astar_step_ratio": result.rl_vs_astar_step_ratio,
                    "astar_plan_ms_avg": result.astar_plan_ms_avg,
                    "rl_plan_ms_avg": result.rl_plan_ms_avg,
                }
            )

    grouped: Dict[str, Dict[str, float]] = {}
    for w, h in sizes:
        k = f"{w}x{h}"
        sub = [r for r in rows if r["width"] == w and r["height"] == h]
        grouped[k] = {
            "runs": len(sub),
            "episodes_per_run": episodes,
            "astar_success_rate_avg": mean(r["astar_success_rate"] for r in sub),
            "rl_success_rate_avg": mean(r["rl_success_rate"] for r in sub),
            "astar_avg_steps_avg": mean(r["astar_avg_steps"] for r in sub),
            "rl_avg_steps_avg": mean(r["rl_avg_steps"] for r in sub),
            "rl_vs_astar_step_ratio_avg": mean(r["rl_vs_astar_step_ratio"] for r in sub),
            "astar_plan_ms_avg": mean(r["astar_plan_ms_avg"] for r in sub),
            "rl_plan_ms_avg": mean(r["rl_plan_ms_avg"] for r in sub),
        }

    return {
        "mode": "multi",
        "sizes": [f"{w}x{h}" for (w, h) in sizes],
        "seeds": seeds,
        "episodes": episodes,
        "per_run": rows,
        "by_size": grouped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="RL vs A* benchmark")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--width", type=int, default=21)
    parser.add_argument("--height", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--multi", action="store_true", help="Run multiple sizes/seeds.")
    parser.add_argument(
        "--sizes",
        type=str,
        default="10x8,15x11,21x15",
        help="Comma-separated sizes for multi mode, e.g. 10x8,15x11,21x15",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="42,43,44",
        help="Comma-separated seeds for multi mode.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Optional output JSON path. If set in multi mode, CSV is also written.",
    )
    args = parser.parse_args()

    if not args.multi:
        result = run_benchmark(args.episodes, args.width, args.height, args.seed)
        payload: Dict = {"mode": "single", **result.__dict__}
        print(json.dumps(payload, indent=2))
        if args.out:
            os.makedirs(os.path.dirname(args.out), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        return

    sizes = _parse_sizes(args.sizes)
    seeds = _parse_seeds(args.seeds)
    payload = run_multi_benchmark(episodes=args.episodes, sizes=sizes, seeds=seeds)
    print(json.dumps(payload["by_size"], indent=2))

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        csv_path = args.out.rsplit(".", 1)[0] + ".csv"
        _write_csv(payload["per_run"], csv_path)
        print(f"\nWrote JSON: {args.out}")
        print(f"Wrote CSV : {csv_path}")


if __name__ == "__main__":
    main()
