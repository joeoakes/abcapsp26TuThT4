"""
RAG (Retrieval-Augmented Generation) module for maze mission data.

Converts mission summaries into 7-dimensional vectors (matching vector/README.md),
stores them in Redis, retrieves top-K similar missions via cosine similarity,
and builds augmented prompts for the LLM.

Supports two backends:
  - RediSearch (FT.CREATE / FT.SEARCH) when the module is loaded
  - Pure-Python fallback scanning Redis keys when RediSearch is unavailable
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import redis as _redis

logger = logging.getLogger(__name__)

VECTOR_DIM = 7
INDEX_NAME = "mission_idx"
MAX_DURATION = 600.0
MAX_DISTANCE = 300.0
TRAJECTORY_PREFIX = "trajectory:"
TRAJECTORY_VEC_DIM = 6

RESULT_MAP = {"success": 1.0, "in_progress": 0.5, "failed": 0.0, "aborted": 0.0}


def _normalize_mission_result(val: str) -> str:
    """Canonical key: success, in_progress, failed, aborted (handles Title Case from Redis)."""
    return str(val or "").strip().lower().replace(" ", "_")


def _result_dimension(val) -> float:
    return RESULT_MAP.get(_normalize_mission_result(str(val)), 0.0)


# ── Vectorization ────────────────────────────────────────────────────

def mission_to_vector(summary: Dict) -> np.ndarray:
    """
    Convert a mission summary hash into a 7-dim float32 vector.

    Dimensions (per vector/README.md):
      0: moves_left_turn  / moves_total
      1: moves_right_turn / moves_total
      2: moves_straight   / moves_total
      3: moves_reverse    / moves_total
      4: duration_seconds / MAX_DURATION
      5: distance_traveled / MAX_DISTANCE
      6: mission_result   -> 1.0 / 0.5 / 0.0
    """
    total = float(summary.get("moves_total", 0)) or 1.0
    vec = np.array([
        float(summary.get("moves_left_turn", 0))  / total,
        float(summary.get("moves_right_turn", 0)) / total,
        float(summary.get("moves_straight", 0))   / total,
        float(summary.get("moves_reverse", 0))    / total,
        min(float(summary.get("duration_seconds", 0)) / MAX_DURATION, 1.0),
        min(float(summary.get("distance_traveled", 0)) / MAX_DISTANCE, 1.0),
        _result_dimension(summary.get("mission_result", "")),
    ], dtype=np.float32)
    return vec


def _vec_to_stored(vec: np.ndarray) -> str:
    """Encode float32 vector as base64 string for safe Redis storage with decode_responses=True."""
    return base64.b64encode(vec.astype(np.float32).tobytes()).decode("ascii")


def _stored_to_vec(raw) -> np.ndarray:
    """Decode a base64-encoded vector string (or raw bytes) back to float32 array."""
    if isinstance(raw, str):
        raw = base64.b64decode(raw)
    elif isinstance(raw, bytes) and len(raw) != VECTOR_DIM * 4:
        raw = base64.b64decode(raw)
    return np.frombuffer(raw, dtype=np.float32).copy()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


# ── RediSearch detection ─────────────────────────────────────────────

def has_redisearch(r: _redis.Redis) -> bool:
    """Check if the RediSearch module is loaded."""
    try:
        modules = r.module_list()
        return any(m.get(b"name", m.get("name", b"")) in (b"search", "search", b"ft", "ft")
                   for m in modules)
    except Exception:
        return False


# ── Index management ─────────────────────────────────────────────────

def ensure_index(r: _redis.Redis) -> bool:
    """
    Create the RediSearch vector index if it doesn't exist.
    Returns True if RediSearch is available, False otherwise.
    """
    if not has_redisearch(r):
        logger.info("RediSearch not available — using Python fallback for similarity search")
        return False

    try:
        r.execute_command("FT.INFO", INDEX_NAME)
        logger.debug("Index '%s' already exists", INDEX_NAME)
        return True
    except _redis.ResponseError:
        pass

    try:
        r.execute_command(
            "FT.CREATE", INDEX_NAME,
            "ON", "HASH",
            "PREFIX", "1", "mission:",
            "SCHEMA",
            "robot_id",          "TEXT",
            "mission_type",      "TAG",
            "mission_result",    "TAG",
            "moves_total",       "NUMERIC",
            "duration_seconds",  "NUMERIC",
            "distance_traveled", "NUMERIC",
            "embedding",         "VECTOR", "FLAT", "6",
                                 "TYPE", "FLOAT32",
                                 "DIM", str(VECTOR_DIM),
                                 "DISTANCE_METRIC", "COSINE",
        )
        logger.info("Created RediSearch index '%s'", INDEX_NAME)
        return True
    except Exception as e:
        logger.warning("Failed to create index: %s", e)
        return False


# ── Store vectors ────────────────────────────────────────────────────

def store_mission_vector(
    r: _redis.Redis,
    mission_id: str,
    summary: Dict,
) -> np.ndarray:
    """
    Compute the vector for a mission and store it at
    ``mission:{mission_id}:vector`` as a Redis hash with an ``embedding`` field.
    Also copies searchable scalar fields so RediSearch can filter on them.
    """
    vec = mission_to_vector(summary)
    key = f"mission:{mission_id}:vector"

    mapping = {
        "embedding":         _vec_to_stored(vec),
        "robot_id":          summary.get("robot_id", ""),
        "mission_type":      summary.get("mission_type", ""),
        "mission_result":    summary.get("mission_result", ""),
        "moves_total":       summary.get("moves_total", 0),
        "duration_seconds":  summary.get("duration_seconds", 0),
        "distance_traveled": summary.get("distance_traveled", 0),
    }
    r.hset(key, mapping=mapping)
    return vec


# ── Retrieval ────────────────────────────────────────────────────────

def search_similar_missions(
    r: _redis.Redis,
    query_vec: np.ndarray,
    top_k: int = 5,
) -> List[Tuple[str, float, Dict]]:
    """
    Find the top-K most similar missions by cosine similarity.

    Returns list of (mission_id, similarity_score, summary_dict) tuples,
    sorted by descending similarity.
    """
    if has_redisearch(r):
        return _search_redisearch(r, query_vec, top_k)
    return _search_fallback(r, query_vec, top_k)


def _search_redisearch(
    r: _redis.Redis,
    query_vec: np.ndarray,
    top_k: int,
) -> List[Tuple[str, float, Dict]]:
    """KNN search via RediSearch FT.SEARCH."""
    blob = query_vec.astype(np.float32).tobytes()
    query = f"*=>[KNN {top_k} @embedding $vec AS score]"

    try:
        raw = r.execute_command(
            "FT.SEARCH", INDEX_NAME, query,
            "PARAMS", "2", "vec", blob,
            "SORTBY", "score", "ASC",
            "LIMIT", "0", str(top_k),
            "RETURN", "3", "score", "mission_result", "moves_total",
            "DIALECT", "2",
        )
    except Exception as e:
        logger.warning("RediSearch query failed: %s — falling back", e)
        return _search_fallback(r, query_vec, top_k)

    results = []
    count = raw[0]
    i = 1
    while i < len(raw):
        key = raw[i] if isinstance(raw[i], str) else raw[i].decode()
        fields = raw[i + 1]
        i += 2

        field_dict = {}
        for j in range(0, len(fields), 2):
            k = fields[j] if isinstance(fields[j], str) else fields[j].decode()
            v = fields[j + 1] if isinstance(fields[j + 1], str) else fields[j + 1].decode()
            field_dict[k] = v

        cosine_dist = float(field_dict.get("score", 1.0))
        similarity = 1.0 - cosine_dist

        mission_id = key.replace("mission:", "").replace(":vector", "")
        summary = _load_summary(r, mission_id)
        results.append((mission_id, similarity, summary))

    return results


def _search_fallback(
    r: _redis.Redis,
    query_vec: np.ndarray,
    top_k: int,
) -> List[Tuple[str, float, Dict]]:
    """Scan all mission:*:vector keys and compute cosine similarity in Python."""
    scored = []

    for key in r.scan_iter(match="mission:*:vector", count=200):
        key_str = key if isinstance(key, str) else key.decode()
        raw_emb = r.hget(key_str, "embedding")
        if raw_emb is None:
            continue

        stored_vec = _stored_to_vec(raw_emb)
        if len(stored_vec) != VECTOR_DIM:
            continue

        sim = cosine_similarity(query_vec, stored_vec)
        mission_id = key_str.replace("mission:", "").replace(":vector", "")
        scored.append((mission_id, sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for mission_id, sim in scored[:top_k]:
        summary = _load_summary(r, mission_id)
        results.append((mission_id, sim, summary))
    return results


def _load_summary(r: _redis.Redis, mission_id: str) -> Dict:
    key = f"mission:{mission_id}:summary"
    data = r.hgetall(key)
    if not data:
        return {}
    return {
        (k if isinstance(k, str) else k.decode()):
        (v if isinstance(v, str) else v.decode())
        for k, v in data.items()
    }


# ── Prompt augmentation ──────────────────────────────────────────────

def build_rag_context(
    similar_missions: List[Tuple[str, float, Dict]],
) -> str:
    """
    Format retrieved missions into a text block suitable for
    injecting into an LLM prompt.
    """
    if not similar_missions:
        return ""

    lines = ["Retrieved similar missions:"]
    for mid, score, summary in similar_missions:
        result = summary.get("mission_result", "unknown")
        total = summary.get("moves_total", "?")
        duration = summary.get("duration_seconds", "?")
        lines.append(
            f"  - {mid}: result={result}, moves={total}, "
            f"duration={duration}s, similarity={score:.3f}"
        )

    successful = [
        s for _, _, s in similar_missions
        if _normalize_mission_result(str(s.get("mission_result", ""))) == "success"
    ]
    failed = [
        s for _, _, s in similar_missions
        if _normalize_mission_result(str(s.get("mission_result", ""))) in ("failed", "aborted")
    ]

    if successful:
        avg_moves = sum(int(s.get("moves_total", 0)) for s in successful) / len(successful)
        lines.append(f"  Avg moves in successful missions: {avg_moves:.0f}")
    if failed:
        avg_moves = sum(int(s.get("moves_total", 0)) for s in failed) / len(failed)
        lines.append(f"  Avg moves in failed missions: {avg_moves:.0f}")

    return "\n".join(lines)


def retrieve_rag_context(
    r: _redis.Redis,
    current_summary: Dict,
    top_k: int = 5,
) -> str:
    """
    End-to-end RAG retrieve step: vectorize the current mission,
    search for similar ones, and format the context string.
    """
    query_vec = mission_to_vector(current_summary)
    similar = search_similar_missions(r, query_vec, top_k=top_k)
    return build_rag_context(similar)


# ── Trajectory memory (maze-structure aware) ─────────────────────────

def _maze_structure_vector(width: int, height: int, cells: list) -> np.ndarray:
    """
    Convert a maze layout into a compact vector for trajectory retrieval.

    Dimensions:
      0) north wall density
      1) east wall density
      2) south wall density
      3) west wall density
      4) dead-end ratio (degree <= 1)
      5) junction ratio (degree >= 3)
    """
    if width <= 0 or height <= 0 or not cells:
        return np.zeros((TRAJECTORY_VEC_DIM,), dtype=np.float32)

    total = float(width * height)
    n = e = s = w = 0
    dead = junction = 0

    for y in range(height):
        for x in range(width):
            walls = int(cells[y * width + x]) & 0xF
            n += 1 if walls & 1 else 0
            e += 1 if walls & 2 else 0
            s += 1 if walls & 4 else 0
            w += 1 if walls & 8 else 0

            degree = 4 - ((1 if walls & 1 else 0) + (1 if walls & 2 else 0) +
                          (1 if walls & 4 else 0) + (1 if walls & 8 else 0))
            if degree <= 1:
                dead += 1
            if degree >= 3:
                junction += 1

    vec = np.array([
        n / total,
        e / total,
        s / total,
        w / total,
        dead / total,
        junction / total,
    ], dtype=np.float32)
    return vec


def store_successful_trajectory(
    r: _redis.Redis,
    maze_sig: str,
    width: int,
    height: int,
    cells: list,
    plan: List[str],
    mission_result: str = "success",
) -> Optional[str]:
    """
    Persist a successful plan keyed by maze signature and structural embedding.
    """
    if not plan:
        return None

    result_key = _normalize_mission_result(mission_result)
    if result_key not in ("success", "in_progress"):
        return None

    vec = _maze_structure_vector(width, height, cells)
    ts = int(time.time() * 1000)
    key = f"{TRAJECTORY_PREFIX}{maze_sig}:{ts}"

    r.hset(
        key,
        mapping={
            "maze_sig": maze_sig,
            "width": width,
            "height": height,
            "plan": json.dumps(plan),
            "plan_len": len(plan),
            "embedding": _vec_to_stored(vec),
            "created_at_ms": ts,
        },
    )
    return key


def retrieve_similar_trajectories(
    r: _redis.Redis,
    maze_sig: str,
    width: int,
    height: int,
    cells: list,
    top_k: int = 3,
    prefix_len: int = 8,
) -> List[Tuple[float, List[str], str]]:
    """
    Returns [(similarity, plan_prefix, source_maze_sig), ...] sorted desc.
    Exact maze_sig matches are prioritized and scored as 1.0.
    """
    if top_k <= 0:
        return []

    query_vec = _maze_structure_vector(width, height, cells)
    scored: List[Tuple[float, List[str], str]] = []

    for key in r.scan_iter(match=f"{TRAJECTORY_PREFIX}*"):
        key_s = key if isinstance(key, str) else key.decode()
        row = r.hgetall(key_s)
        if not row:
            continue

        src_sig = row.get("maze_sig", "")
        raw_plan = row.get("plan")
        raw_embedding = row.get("embedding")
        if not raw_plan or not raw_embedding:
            continue

        try:
            plan = json.loads(raw_plan)
        except Exception:
            continue
        if not isinstance(plan, list) or not plan:
            continue

        if src_sig == maze_sig:
            sim = 1.0
        else:
            vec = _stored_to_vec(raw_embedding)
            if len(vec) != TRAJECTORY_VEC_DIM:
                continue
            sim = cosine_similarity(query_vec, vec)

        scored.append((float(sim), plan[:prefix_len], src_sig))

    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:top_k]


def build_trajectory_context(snippets: List[Tuple[float, List[str], str]]) -> str:
    if not snippets:
        return ""
    lines = ["Retrieved successful trajectory snippets:"]
    for i, (sim, prefix, sig) in enumerate(snippets, start=1):
        lines.append(
            f"  {i}. maze_sig={sig[:12]}..., similarity={sim:.3f}, "
            f"prefix={json.dumps(prefix)}"
        )
    return "\n".join(lines)
