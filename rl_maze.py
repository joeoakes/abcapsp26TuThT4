"""
Tabular Q-learning planner for maze navigation.

Pattern #1 implementation:
- Uses reward shaping from A* heuristic (Manhattan distance delta).
- Learns online from expert A* plans and can consume trajectory hints from RAG.
- Returns a legal plan or None when confidence is too low.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from tools_maze import DIRECTIONS, astar, legal_moves

# Stable action order for deterministic tie-breaking
ACTIONS: List[str] = ["UP", "RIGHT", "DOWN", "LEFT"]


def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _cell_walls(width: int, cells: list, x: int, y: int) -> int:
    return int(cells[y * width + x])


def _clip_rel(v: int, cap: int = 10) -> int:
    return max(-cap, min(cap, v))


def _state_key(
    width: int,
    cells: list,
    x: int,
    y: int,
    gx: int,
    gy: int,
) -> Tuple[int, int, int, int, int]:
    """
    Compact transferable state:
    - clipped relative goal dx,dy
    - local 4-bit wall mask
    """
    walls = _cell_walls(width, cells, x, y) & 0xF
    return (_clip_rel(gx - x), _clip_rel(gy - y), walls, x, y)


def _next_pos(x: int, y: int, move: str) -> Tuple[int, int]:
    dx, dy = DIRECTIONS[move][0], DIRECTIONS[move][1]
    return x + dx, y + dy


@dataclass
class QLearningPlanner:
    alpha: float = 0.35
    gamma: float = 0.95
    epsilon: float = 0.08
    shaping_weight: float = 0.5
    q: Dict[Tuple[int, int, int, int, int], Dict[str, float]] = field(default_factory=dict)
    rng: random.Random = field(default_factory=lambda: random.Random(0))

    def _ensure_state(self, key: Tuple[int, int, int, int, int]) -> Dict[str, float]:
        if key not in self.q:
            self.q[key] = {a: 0.0 for a in ACTIONS}
        return self.q[key]

    def _best_action(
        self,
        key: Tuple[int, int, int, int, int],
        legal: List[str],
    ) -> Optional[str]:
        if not legal:
            return None
        qvals = self._ensure_state(key)
        return max(legal, key=lambda a: (qvals[a], -ACTIONS.index(a)))

    def _update(
        self,
        state_key: Tuple[int, int, int, int, int],
        action: str,
        reward: float,
        next_state_key: Tuple[int, int, int, int, int],
        next_legal: List[str],
    ) -> None:
        qvals = self._ensure_state(state_key)
        next_vals = self._ensure_state(next_state_key)
        max_next = max((next_vals[a] for a in next_legal), default=0.0)
        qvals[action] = qvals[action] + self.alpha * (
            reward + self.gamma * max_next - qvals[action]
        )

    def _step_reward(
        self,
        prev: Tuple[int, int],
        nxt: Tuple[int, int],
        goal: Tuple[int, int],
        is_goal: bool,
    ) -> float:
        # Base step cost + potential-based shaping from A* heuristic proxy.
        prev_h = _manhattan(prev, goal)
        next_h = _manhattan(nxt, goal)
        shaping = self.shaping_weight * float(prev_h - next_h)
        reward = -1.0 + shaping
        if is_goal:
            reward += 100.0
        return reward

    def fit_with_astar(
        self,
        width: int,
        height: int,
        cells: list,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        episodes: int = 20,
        max_steps: int = 1000,
        trajectory_hints: Optional[List[List[str]]] = None,
    ) -> Optional[List[str]]:
        """
        Train tabular Q-values with A* as expert and return the expert plan.
        """
        expert = astar(width, height, cells, start, goal)
        if expert is None:
            return None

        # Supervised warm start: one optimistic update along expert trajectory.
        x, y = start
        for move in expert:
            s = _state_key(width, cells, x, y, goal[0], goal[1])
            nx, ny = _next_pos(x, y, move)
            s2 = _state_key(width, cells, nx, ny, goal[0], goal[1])
            legal2 = legal_moves(width, height, cells, nx, ny)
            reward = self._step_reward((x, y), (nx, ny), goal, (nx, ny) == goal) + 8.0
            self._update(s, move, reward, s2, legal2)
            x, y = nx, ny

        self._apply_hints(width, height, cells, start, goal, trajectory_hints or [])

        # Q-learning episodes with epsilon-greedy exploration.
        for _ in range(max(1, episodes)):
            x, y = start
            for _step in range(max_steps):
                if (x, y) == goal:
                    break
                s = _state_key(width, cells, x, y, goal[0], goal[1])
                legal = legal_moves(width, height, cells, x, y)
                if not legal:
                    break

                if self.rng.random() < self.epsilon:
                    action = self.rng.choice(legal)
                else:
                    action = self._best_action(s, legal)
                    if action is None:
                        break

                nx, ny = _next_pos(x, y, action)
                s2 = _state_key(width, cells, nx, ny, goal[0], goal[1])
                legal2 = legal_moves(width, height, cells, nx, ny)
                reward = self._step_reward((x, y), (nx, ny), goal, (nx, ny) == goal)

                # Mild expert prior: prefer expert action at this step index.
                step_idx = _step
                if step_idx < len(expert) and action == expert[step_idx]:
                    reward += 2.0

                self._update(s, action, reward, s2, legal2)
                x, y = nx, ny

        return expert

    def _apply_hints(
        self,
        width: int,
        height: int,
        cells: list,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        hints: List[List[str]],
    ) -> None:
        """
        Warm-start Q-values from retrieved successful trajectory prefixes.
        """
        for hint in hints:
            x, y = start
            for move in hint:
                legal = legal_moves(width, height, cells, x, y)
                if move not in legal:
                    break
                s = _state_key(width, cells, x, y, goal[0], goal[1])
                self._ensure_state(s)[move] += 0.25
                x, y = _next_pos(x, y, move)

    def greedy_plan(
        self,
        width: int,
        height: int,
        cells: list,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        max_steps: int = 1000,
    ) -> Optional[List[str]]:
        """
        Roll out the current greedy policy into a move sequence.
        """
        x, y = start
        plan: List[str] = []
        seen_counts: Dict[Tuple[int, int], int] = {(x, y): 1}

        for _ in range(max_steps):
            if (x, y) == goal:
                return plan

            legal = legal_moves(width, height, cells, x, y)
            if not legal:
                return None

            s = _state_key(width, cells, x, y, goal[0], goal[1])
            action = self._best_action(s, legal)
            if action is None:
                return None

            nx, ny = _next_pos(x, y, action)
            if seen_counts.get((nx, ny), 0) >= 3:
                # Escape short loops using heuristic tie-break.
                action = min(legal, key=lambda a: _manhattan(_next_pos(x, y, a), goal))
                nx, ny = _next_pos(x, y, action)

            plan.append(action)
            x, y = nx, ny
            seen_counts[(x, y)] = seen_counts.get((x, y), 0) + 1

        return None


_PLANNERS: Dict[str, QLearningPlanner] = {}


def get_session_planner(session_id: str) -> QLearningPlanner:
    if session_id not in _PLANNERS:
        _PLANNERS[session_id] = QLearningPlanner()
    return _PLANNERS[session_id]

