# Telemetry System

## Overview

The maze game sends real-time telemetry data via HTTPS to multiple servers on every player action. All data is encrypted in transit using TLS with self-signed certificates.

---

## Architecture

```
Maze Game (SDL2 Client)
    │
    ├── HTTPS POST /telemetry ──→ Logging Server (10.170.8.101:8446) → MongoDB
    ├── HTTPS POST /telemetry ──→ MiniPupper    (10.170.8.123:8446) → stdout
    └── HTTPS POST /mission   ──→ AI Server     (10.170.8.109:8446) → Redis
```

---

## Telemetry Payload

Sent to **Logging Server** and **MiniPupper** on every player move, game reset, win, and startup.

### Endpoint

```
POST /telemetry
Content-Type: application/json
```

### Payload Schema

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier (UUID format) |
| `event_type` | string | Type of event (see Event Types below) |
| `goal_reached` | boolean | Whether the player has reached the goal |
| `timestamp` | string | UTC timestamp in ISO 8601 format |
| `move_sequence` | int | Sequential move counter for the session |
| `x` | int | Player X position in the maze grid |
| `y` | int | Player Y position in the maze grid |

### Event Types

| Event | When It Fires |
|-------|---------------|
| `startup` | Game launches (connectivity test) |
| `player_move` | Player moves with arrow keys |
| `player_won` | Player reaches the green goal |
| `maze_reset` | Player presses R to reset |

### Example Payloads

**Player Move:**
```json
{
  "session_id": "team4-20260220-052329-c7e8e2495c0d5177",
  "event_type": "player_move",
  "goal_reached": false,
  "timestamp": "2026-02-20T05:24:15Z",
  "move_sequence": 12,
  "x": 4,
  "y": 3
}
```

**Player Won:**
```json
{
  "session_id": "team4-20260220-052329-c7e8e2495c0d5177",
  "event_type": "player_won",
  "goal_reached": true,
  "timestamp": "2026-02-20T05:26:42Z",
  "move_sequence": 143,
  "x": 20,
  "y": 14
}
```

**Startup (Connectivity Test):**
```json
{
  "session_id": "team4-20260220-052329-c7e8e2495c0d5177",
  "event_type": "startup",
  "goal_reached": false,
  "timestamp": "2026-02-20T05:23:30Z",
  "move_sequence": 0,
  "x": 0,
  "y": 0
}
```

---

## Mission Payload

Sent to the **AI Server** on every player move and win. Contains cumulative mission statistics for the current session.

### Endpoint

```
POST /mission
Content-Type: application/json
```

### Payload Schema

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier |
| `moves_left_turn` | int | Total left moves this session |
| `moves_right_turn` | int | Total right moves this session |
| `moves_straight` | int | Total forward moves this session |
| `moves_reverse` | int | Total backward moves this session |
| `mission_won` | boolean | Whether the goal has been reached |

### Example Payload

```json
{
  "session_id": "team4-20260220-052329-c7e8e2495c0d5177",
  "moves_left_turn": 25,
  "moves_right_turn": 45,
  "moves_straight": 28,
  "moves_reverse": 42,
  "mission_won": false
}
```

---

## curl Test Commands

### Test Logging Server (MongoDB)

```bash
curl -k -X POST https://10.170.8.101:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "curl-test-001",
    "event_type": "player_move",
    "goal_reached": false,
    "timestamp": "2026-02-20T12:00:00Z",
    "move_sequence": 1,
    "x": 3,
    "y": 2
  }'
```

Expected response: `{"status":"ok"}`

### Test AI Server (Redis)

```bash
curl -k -X POST https://10.170.8.109:8446/mission \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "curl-test-001",
    "moves_left_turn": 5,
    "moves_right_turn": 8,
    "moves_straight": 12,
    "moves_reverse": 3,
    "mission_won": false
  }'
```

Expected response: `{"status":"ok"}`

### Test MiniPupper

```bash
curl -k -X POST https://10.170.8.123:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "curl-test-001",
    "event_type": "player_move",
    "goal_reached": false,
    "timestamp": "2026-02-20T12:00:00Z",
    "move_sequence": 1,
    "x": 3,
    "y": 2
  }'
```

Expected response: `{"status":"ok"}`

### Quick Health Check (All Servers)

```bash
echo "--- Logging Server ---"
curl -sk -X POST https://10.170.8.101:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{"session_id":"healthcheck","event_type":"ping","goal_reached":false,"timestamp":"2026-02-20T00:00:00Z","move_sequence":0,"x":0,"y":0}' && echo ""

echo "--- AI Server ---"
curl -sk -X POST https://10.170.8.109:8446/mission \
  -H "Content-Type: application/json" \
  -d '{"session_id":"healthcheck","mission_won":false,"moves_left_turn":0,"moves_right_turn":0,"moves_straight":0,"moves_reverse":0}' && echo ""

echo "--- MiniPupper ---"
curl -sk -X POST https://10.170.8.123:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{"session_id":"healthcheck","event_type":"ping","goal_reached":false,"timestamp":"2026-02-20T00:00:00Z","move_sequence":0,"x":0,"y":0}' && echo ""
```

All should return `{"status":"ok"}`.

---

## Where Data is Stored

| Server | Storage | How to Check |
|--------|---------|--------------|
| Logging Server (10.170.8.101) | MongoDB `maze.team4ttmoves` | `mongosh maze --eval "db.team4ttmoves.find().sort({_id:-1}).limit(3)"` |
| AI Server (10.170.8.109) | Redis `mission:queue` and `mission:latest` | `redis-cli LRANGE mission:queue -1 -1` |
| MiniPupper (10.170.8.123) | stdout (printed to terminal) | Check the terminal running the server |

---

## Server Details

| Server | IP | Port | Endpoint | Backend | Binary |
|--------|----|------|----------|---------|--------|
| Logging | 10.170.8.101 | 8446 | `/telemetry` | MongoDB | `maze_https_mongo` |
| AI | 10.170.8.109 | 8446 | `/mission` | Redis | `maze_https_redis` |
| MiniPupper | 10.170.8.123 | 8446 | `/telemetry` | stdout | `maze_https_telemetry` |

---

## Security

- All communication uses **HTTPS (TLS)**
- Self-signed certificates for development (`certs/server.crt`, `certs/server.key`)
- SSL verification disabled on client side for self-signed certs
- HTTPS requests run in **background threads** so the game is never blocked

---

## Local Redis (Mission Dashboard)

In addition to the remote servers, the maze game writes mission tracking data to **local Redis** (`127.0.0.1:6379`) for the in-game mission dashboard.

### Redis Hash Schema: `mission:{session_id}:summary`

| Field | Type | Description |
|-------|------|-------------|
| `robot_id` | string | Player identifier |
| `mission_type` | string | Mission type (e.g. `explore`) |
| `start_time` | string | Epoch seconds |
| `end_time` | string | Epoch seconds |
| `moves_left_turn` | int | Left move count |
| `moves_right_turn` | int | Right move count |
| `moves_straight` | int | Forward move count |
| `moves_reverse` | int | Backward move count |
| `moves_total` | int | Total moves |
| `distance_traveled` | float | Estimated distance |
| `duration_seconds` | int | Mission duration |
| `mission_result` | string | `success`, `in_progress`, or `failed` |
| `abort_reason` | string | Reason if aborted |

Press **L** during gameplay to view the mission dashboard in the terminal.
