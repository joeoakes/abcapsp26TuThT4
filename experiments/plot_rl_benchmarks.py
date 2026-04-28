#!/usr/bin/env python3
"""
Plot RL-vs-A* benchmark results produced by benchmark_rl_astar.py.

Usage:
  ./.venv/bin/python experiments/plot_rl_benchmarks.py \
      --input experiments/results/rl_astar_multi.json \
      --outdir experiments/results
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List


def _load_payload(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_summary_text(payload: Dict, out_path: str) -> None:
    lines: List[str] = []
    lines.append("RL vs A* Benchmark Summary")
    lines.append("")
    by_size = payload.get("by_size", {})
    if not by_size:
        lines.append("No by_size aggregate present in input JSON.")
    else:
        for size, stats in by_size.items():
            lines.append(f"{size}:")
            lines.append(f"  rl_success_rate_avg      = {stats['rl_success_rate_avg']:.3f}")
            lines.append(f"  astar_success_rate_avg   = {stats['astar_success_rate_avg']:.3f}")
            lines.append(f"  rl_vs_astar_step_ratio   = {stats['rl_vs_astar_step_ratio_avg']:.3f}")
            lines.append(f"  rl_plan_ms_avg           = {stats['rl_plan_ms_avg']:.3f}")
            lines.append(f"  astar_plan_ms_avg        = {stats['astar_plan_ms_avg']:.3f}")
            lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")


def _plot_with_matplotlib(payload: Dict, outdir: str) -> List[str]:
    import matplotlib.pyplot as plt  # type: ignore

    by_size = payload.get("by_size", {})
    if not by_size:
        raise ValueError("Input JSON has no 'by_size' section; run benchmark with --multi.")

    sizes = list(by_size.keys())
    rl_success = [by_size[s]["rl_success_rate_avg"] for s in sizes]
    astar_success = [by_size[s]["astar_success_rate_avg"] for s in sizes]
    step_ratio = [by_size[s]["rl_vs_astar_step_ratio_avg"] for s in sizes]
    rl_ms = [by_size[s]["rl_plan_ms_avg"] for s in sizes]
    astar_ms = [by_size[s]["astar_plan_ms_avg"] for s in sizes]

    os.makedirs(outdir, exist_ok=True)
    out_files = []

    # Figure 1: success rate
    fig1, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.plot(sizes, rl_success, marker="o", label="RL success rate")
    ax1.plot(sizes, astar_success, marker="o", label="A* success rate")
    ax1.set_ylim(0, 1.05)
    ax1.set_title("Success Rate by Maze Size")
    ax1.set_ylabel("Success Rate")
    ax1.set_xlabel("Maze Size")
    ax1.grid(alpha=0.25)
    ax1.legend()
    p1 = os.path.join(outdir, "rl_astar_success_rate.png")
    fig1.tight_layout()
    fig1.savefig(p1, dpi=160)
    out_files.append(p1)
    plt.close(fig1)

    # Figure 2: path quality ratio (RL/A*)
    fig2, ax2 = plt.subplots(figsize=(8, 4.5))
    ax2.plot(sizes, step_ratio, marker="o", color="#2ca02c")
    ax2.axhline(1.0, linestyle="--", color="#666666", linewidth=1)
    ax2.set_title("Path Quality: RL Steps / A* Steps")
    ax2.set_ylabel("Ratio (1.0 = parity)")
    ax2.set_xlabel("Maze Size")
    ax2.grid(alpha=0.25)
    p2 = os.path.join(outdir, "rl_astar_step_ratio.png")
    fig2.tight_layout()
    fig2.savefig(p2, dpi=160)
    out_files.append(p2)
    plt.close(fig2)

    # Figure 3: planning latency
    fig3, ax3 = plt.subplots(figsize=(8, 4.5))
    ax3.plot(sizes, rl_ms, marker="o", label="RL planning ms")
    ax3.plot(sizes, astar_ms, marker="o", label="A* planning ms")
    ax3.set_title("Planner Latency by Maze Size")
    ax3.set_ylabel("Milliseconds")
    ax3.set_xlabel("Maze Size")
    ax3.grid(alpha=0.25)
    ax3.legend()
    p3 = os.path.join(outdir, "rl_astar_latency_ms.png")
    fig3.tight_layout()
    fig3.savefig(p3, dpi=160)
    out_files.append(p3)
    plt.close(fig3)

    return out_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot RL benchmark results")
    parser.add_argument("--input", required=True, help="Path to benchmark JSON.")
    parser.add_argument("--outdir", default="experiments/results", help="Output directory.")
    args = parser.parse_args()

    payload = _load_payload(args.input)
    os.makedirs(args.outdir, exist_ok=True)

    summary_path = os.path.join(args.outdir, "rl_astar_summary.txt")
    _save_summary_text(payload, summary_path)
    print(f"Wrote summary: {summary_path}")

    try:
        files = _plot_with_matplotlib(payload, args.outdir)
    except ImportError:
        print(
            "matplotlib is not installed. Install it with:\n"
            "  ./.venv/bin/pip install matplotlib\n"
            "Then rerun this script to generate PNG charts."
        )
        sys.exit(0)

    print("Wrote charts:")
    for p in files:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
