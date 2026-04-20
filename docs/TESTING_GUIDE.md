# Team4 Maze App — Testing Guide

## Architecture

```
                Maze App (GameHat Controller 10.170.8.189)
               /                |                        \
              v                 v                         v
        HTTPS POST        HTTPS POST                HTTPS POST
       /telemetry         /telemetry                 /mission
            |                  |                        |
     Mini Pupper        Logging Server             AI Server
     10.170.8.123       10.170.8.130              10.170.8.109
       [ROS2]             [MongoDB]                 [Redis]
```

---

## mTLS Setup (One-Time)

All HTTPS servers and the maze client use **mutual TLS**. One person (cert coordinator) generates certs once, then copies to all servers and clients.

**Full deployment steps:** See [MTLS_DEPLOYMENT.md](MTLS_DEPLOYMENT.md)

**Quick generate (cert coordinator only):**
```bash
cd ~/abcapsp26TuThT4/https/certs
./gen_mtls_certs.sh
```

Then copy server certs to each server, client certs to each client. See MTLS_DEPLOYMENT.md for exact commands.

---

## SSH Credentials

| Machine | Command | Password |
|---------|---------|----------|
| GameHat Controller | `ssh pi@10.170.8.189` | `raspberry` |
| Mini Pupper | `ssh ubuntu@10.170.8.123` | `mangdang` |
| Logging Server | `ssh UNIQUE_LOGIN@10.170.8.130` | `UNIQUE_PASSWORD` |
| AI Server | `ssh UNIQUE_LOGIN@10.170.8.109` | `UNIQUE_PASSWORD` |

---

## Step 1: Verify Logging Server (MongoDB)

### 1A. Check the server is running

```bash
ssh UNIQUE_LOGIN@10.170.8.130
```

```bash
ss -lntp | grep 8446
```

You should see `maze_https_mong` listening on port 8446. If NOT running:

```bash
cd ~/abcapsp26TuThT4/https
./maze_https_mongo
```

### 1B. Test the endpoint

From **any machine** on the network:

```bash
cd ~/abcapsp26TuThT4/https
curl --cert certs/client.crt --key certs/client.key --cacert certs/ca.crt \
  -X POST https://10.170.8.130:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{"session_id":"teammate-test","event_type":"connectivity_test","x":0,"y":0,"goal_reached":false,"timestamp":"2026-02-17T12:00:00Z","move_sequence":0}'
```

**Expected:** `{"status":"ok"}`

### 1C. Verify data in MongoDB

On the Logging Server:

```bash
mongosh
```

```javascript
use maze
db.team4ttmoves.countDocuments()
db.team4ttmoves.find().sort({_id:-1}).limit(1)
```

You should see your test document with a `received_at` timestamp.

Type `exit` to leave mongosh.

---

## Step 2: Verify AI Server (Redis)

### 2A. Check the server is running

```bash
ssh UNIQUE_LOGIN@10.170.8.109
```

```bash
ss -lntp | grep 8446
```

You should see `maze_https_redi` listening on port 8446. If NOT running:

```bash
cd ~/abcapsp26TuThT4/https
./maze_https_redis
```

### 2B. Verify Redis is working

```bash
redis-cli ping
```

**Expected:** `PONG`

### 2C. Test the endpoint

From **any machine** on the network:

```bash
cd ~/abcapsp26TuThT4/https
curl --cert certs/client.crt --key certs/client.key --cacert certs/ca.crt \
  -X POST https://10.170.8.109:8446/mission \
  -H "Content-Type: application/json" \
  -d '{"session_id":"teammate-test","moves_left_turn":3,"moves_right_turn":5,"moves_straight":10,"moves_reverse":2,"mission_won":false}'
```

**Expected:** `{"status":"ok"}`

### 2D. Verify data in Redis

On the AI Server:

```bash
redis-cli
```

```
LLEN mission:queue
LRANGE mission:queue -1 -1
GET mission:latest
```

You should see the test JSON payload. Type `exit` to leave redis-cli.

---

## Step 3: Run the Maze Game

### 3A. Build on your dev machine (WSL / Linux)

Install dependencies (one time):

```bash
sudo apt update
sudo apt install -y build-essential pkg-config libsdl2-dev \
    libcurl4-openssl-dev libcjson-dev libhiredis-dev redis-server
```

Start local Redis (for mission tracking):

```bash
sudo service redis-server start
```

### 3B. Build the maze game

```bash
cd ~/abcapsp26TuThT4/maze
gcc -O2 -Wall -std=c11 maze_sdl2_final_send.c -o maze_game \
    $(pkg-config --cflags --libs sdl2) -lcurl -lcjson -lhiredis -lpthread
```

### 3C. Run

```bash
./maze_game
```

### 3D. What to expect

- A maze window opens
- Use **arrow keys** to move the yellow square to the green goal
- In the terminal you should see:

```
[OK] Logging server
[OK] AI server
[ERROR] MiniPupper          <-- expected until Mini Pupper server is deployed
```

- The game should be **responsive with no lag** (HTTPS requests run in background threads)
- When you reach the green square: window title changes to "You win!"

---

## Step 4: Verify Real-Time Data After Playing

### Check MongoDB received your moves

```bash
ssh UNIQUE_LOGIN@10.170.8.130
mongosh
```

```javascript
use maze
db.team4ttmoves.countDocuments()
db.team4ttmoves.find().sort({_id:-1}).limit(3)
```

You should see your `player_move` and `player_won` events with your session ID.

### Check Redis received your mission data

```bash
ssh UNIQUE_LOGIN@10.170.8.109
redis-cli
```

```
GET mission:latest
LLEN mission:queue
```

You should see your latest mission summary with move counts and `mission_won` status.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `curl: (7) Connection refused` | Server isn't running — SSH in and start it |
| `Failed to start HTTPS server` | Port 8446 already in use — run `ss -lntp \| grep 8446`, kill the old PID, restart |
| Game freezes on move | Rebuild with `-lpthread` flag |
| `Redis connection failed` | Start Redis: `sudo service redis-server start` |
| `[ERROR] MiniPupper` | Expected — Mini Pupper server not deployed yet |
| Build errors about `enum MHD_Result` | Make sure `#define _GNU_SOURCE` is at the top of the .c file |
| `Client certificate required` (401) | Provide client cert: `--cert certs/client.crt --key certs/client.key --cacert certs/ca.crt` |
| `mTLS cert files not found` | Run `./gen_mtls_certs.sh` in https/certs, run maze from project root |

---

## File Locations on Servers

| Server | Binary Path |
|--------|-------------|
| Logging Server (10.170.8.130) | `~/abcapsp26TuThT4/https/maze_https_mongo` |
| AI Server (10.170.8.109) | `~/abcapsp26TuThT4/https/maze_https_redis` |
| Mini Pupper (10.170.8.123) | Not deployed yet |

---

## Quick Health Check (All Servers at Once)

Run from project root. With mTLS, you must provide client cert, key, and CA:

```bash
cd ~/abcapsp26TuThT4/https

echo "--- Logging Server ---"
curl --cert certs/client.crt --key certs/client.key --cacert certs/ca.crt \
  -X POST https://10.170.8.130:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{"session_id":"healthcheck","event_type":"ping"}' && echo ""

echo "--- AI Server ---"
curl --cert certs/client.crt --key certs/client.key --cacert certs/ca.crt \
  -X POST https://10.170.8.109:8446/mission \
  -H "Content-Type: application/json" \
  -d '{"session_id":"healthcheck","mission_won":false}' && echo ""
```

Both should print `{"status":"ok"}`.

---

## mTLS Verification Tests

Use these to confirm mTLS is working correctly.

### Test 1: Without client cert — should get 401

```bash
cd ~/abcapsp26TuThT4/https
curl -k -X POST https://localhost:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{"session_id":"no-cert-test"}'
```

**Expected:** `Client certificate required` (HTTP 401). If you get `{"status":"ok"}`, mTLS is not enforcing client certs.

### Test 2: With client cert — should get 200

```bash
cd ~/abcapsp26TuThT4/https
curl --cert certs/client.crt --key certs/client.key --cacert certs/ca.crt \
  -X POST https://localhost:8446/telemetry \
  -H "Content-Type: application/json" \
  -d '{"session_id":"mtls-test","event_type":"connectivity_test","x":0,"y":0}'
```

**Expected:** `{"status":"ok"}`. Server should log `Client DN: ...` in its terminal.

### Test 3: Local end-to-end (one machine)

1. Start Redis: `sudo service redis-server start`
2. Start the Redis server: `cd ~/abcapsp26TuThT4/https && ./maze_https_redis` (in one terminal)
3. Run Test 2 above (in another terminal) — should succeed
4. Run the maze game: `cd ~/abcapsp26TuThT4 && ./maze/maze_sdl2_final_send` — should show `[OK]` for servers
