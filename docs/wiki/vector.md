# Vector Database Schema – Maze / Mission Data

## Overview

This folder defines the schema for storing maze mission data in a **Redis Vector Database** for use by the AI RAG (Retrieval-Augmented Generation) system.

---

## Mission Data Schema

### Redis Hash: `mission:{mission_id}:summary`

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `robot_id` | string | Robot or player identifier | `keyboard-player` |
| `mission_type` | string | Type of mission | `patrol`, `explore`, `follow`, `delivery`, `search` |
| `start_time` | string | Mission start (epoch seconds) | `1770582849` |
| `end_time` | string | Mission end (epoch seconds) | `1770582912` |
| `moves_left_turn` | int | Number of left moves | `25` |
| `moves_right_turn` | int | Number of right moves | `45` |
| `moves_straight` | int | Number of forward moves | `28` |
| `moves_reverse` | int | Number of backward moves | `42` |
| `moves_total` | int | Total moves | `140` |
| `distance_traveled` | float | Estimated distance | `54.60` |
| `duration_seconds` | int | Mission duration in seconds | `63` |
| `mission_result` | string | Outcome of mission | `success`, `in_progress`, `failed`, `aborted` |
| `abort_reason` | string | Reason if aborted/failed | `user exited`, `user reset`, `""` |

---

## Vector Database Schema

### Purpose

The vector representation allows **similarity search** across missions so the RAG system can find missions with similar behavior patterns (e.g. "find missions that look like this failed one").

### Vector Dimensions

Each mission is converted into a **numeric vector** with the following dimensions:

| Dimension | Field | Description | Normalization |
|-----------|-------|-------------|---------------|
| Dim 1 | `moves_left_turn` | Left turn ratio | `moves_left_turn / moves_total` |
| Dim 2 | `moves_right_turn` | Right turn ratio | `moves_right_turn / moves_total` |
| Dim 3 | `moves_straight` | Forward move ratio | `moves_straight / moves_total` |
| Dim 4 | `moves_reverse` | Reverse move ratio | `moves_reverse / moves_total` |
| Dim 5 | `duration_seconds` | Mission duration (normalized) | `duration_seconds / max_duration` |
| Dim 6 | `distance_traveled` | Distance (normalized) | `distance_traveled / max_distance` |
| Dim 7 | `mission_result` | Outcome as numeric | `1.0` = success, `0.5` = in_progress, `0.0` = failed |

### Example

| Mission | Dim 1 | Dim 2 | Dim 3 | Dim 4 | Dim 5 | Dim 6 | Dim 7 |
|---------|-------|-------|-------|-------|-------|-------|-------|
| mission-A | 0.18 | 0.32 | 0.20 | 0.30 | 0.45 | 0.55 | 1.0 |
| mission-B | 0.25 | 0.25 | 0.25 | 0.25 | 0.80 | 0.40 | 0.0 |
| mission-C | 0.10 | 0.50 | 0.15 | 0.25 | 0.30 | 0.60 | 1.0 |

**Observations:**
- mission-A and mission-C are both successful with similar right-turn-heavy patterns
- mission-B has equal movement distribution but took longer and failed
- RAG can use these vectors to find similar missions and recommend strategies

---

## Redis Key Structure

### Real-Time Mission Data (Hash)

```
Key:   mission:{mission_id}:summary
Type:  Hash
```

```bash
# Example
redis-cli HGETALL "mission:d2f45c27-7c21-ab71-926d-26ab1f117d24:summary"
```

### Vector Embeddings (for RediSearch)

```
Key:   mission:{mission_id}:vector
Type:  Hash with VECTOR field
```

```bash
# Index creation (RediSearch / Redis Stack)
FT.CREATE mission_idx ON HASH PREFIX 1 "mission:" SCHEMA
  robot_id TEXT
  mission_type TAG
  mission_result TAG
  moves_total NUMERIC
  duration_seconds NUMERIC
  distance_traveled NUMERIC
  embedding VECTOR FLAT 6
    TYPE FLOAT32
    DIM 7
    DISTANCE_METRIC COSINE
```

---

## RAG Integration

### How RAG Uses This Data

1. **Retrieve** – Query the vector database for missions similar to the current one
2. **Augment** – Combine retrieved mission data with the user's question
3. **Generate** – LLM (on Spark DGX server) generates analysis and recommendations

### Example RAG Queries

- "Summarize the main causes of failure across the retrieved missions"
- "Compare successful vs failed missions for maze_id=maze-7"
- "Recommend 3 pathway heuristics based on the retrieved successful missions"
- "What behavioral patterns lead to mission failure?"

### Query Flow

```
User Query
    ↓
Convert to vector embedding
    ↓
Search Redis Vector DB (cosine similarity)
    ↓
Retrieve top-K similar missions
    ↓
Build prompt with mission data
    ↓
Send to LLM (Spark DGX)
    ↓
Return analysis/recommendations
```

---

## Data Flow

```
Maze Game (SDL2)
    ↓ (on each move)
Redis Hash: mission:{id}:summary     ← Real-time mission data
    ↓ (on mission complete)
Redis Vector: mission:{id}:vector    ← Numeric vector for similarity search
    ↓ (on RAG query)
RAG App → Vector Search → LLM → Response
```

---

## Sample Data

### Create test mission data

```bash
redis-cli HSET mission:TEST_MISSION:summary \
  robot_id keyboard-player \
  mission_type explore \
  start_time 1770330033 \
  end_time 1770330064 \
  moves_left_turn 27 \
  moves_right_turn 32 \
  moves_straight 47 \
  moves_reverse 8 \
  moves_total 114 \
  distance_traveled 24.41 \
  duration_seconds 31 \
  mission_result success \
  abort_reason ""
```

### Verify

```bash
redis-cli HGETALL "mission:TEST_MISSION:summary"
```

---

## Dependencies

- **Redis** (v7.0+) – Base database
- **Redis Stack** or **RediSearch module** – For vector similarity search
- **Python redis** + **numpy** – For generating and storing vectors
- **LLM API** (Spark DGX server) – For RAG generation
