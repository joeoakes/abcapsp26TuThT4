# mTLS Certificate Deployment Guide

One person (the **cert coordinator**) generates certs once, then copies them to all servers and clients. Everyone on the team uses the same certs.

---

## Step 1: Generate Certificates (Cert Coordinator Only)

Run this **once** on your local machine:

```bash
cd ~/abcapsp26TuThT4/https/certs
./gen_mtls_certs.sh
```

This creates:
- `ca.crt`, `ca.key` (CA)
- `server.crt`, `server.key` (for all HTTPS servers)
- `client.crt`, `client.key` (for maze client / GameHat)

---

## Step 2: Copy Server Certs to Each Server

From your machine (where you ran the script):

```bash
cd ~/abcapsp26TuThT4/https

# Create certs directory on each server (if it doesn't exist)
ssh UNIQUE_LOGIN@10.170.8.130 "mkdir -p ~/abcapsp26TuThT4/https/certs"
ssh UNIQUE_LOGIN@10.170.8.109 "mkdir -p ~/abcapsp26TuThT4/https/certs"
ssh ubuntu@10.170.8.123 "mkdir -p ~/abcapsp26TuThT4/https/certs"

# Copy server.crt, server.key, ca.crt to each server
scp certs/server.crt certs/server.key certs/ca.crt UNIQUE_LOGIN@10.170.8.130:~/abcapsp26TuThT4/https/certs/
scp certs/server.crt certs/server.key certs/ca.crt UNIQUE_LOGIN@10.170.8.109:~/abcapsp26TuThT4/https/certs/
scp certs/server.crt certs/server.key certs/ca.crt ubuntu@10.170.8.123:~/abcapsp26TuThT4/https/certs/
```

| Server | IP | User | Path |
|--------|-----|------|------|
| Logging | 10.170.8.130 | UNIQUE_LOGIN | `~/abcapsp26TuThT4/https/certs/` |
| AI | 10.170.8.109 | UNIQUE_LOGIN | `~/abcapsp26TuThT4/https/certs/` |
| MiniPupper | 10.170.8.123 | ubuntu | `~/abcapsp26TuThT4/https/certs/` |

---

## Step 3: Copy Client Certs to Each Client

**Option A: GameHat / Raspberry Pi (remote client)**

```bash
cd ~/abcapsp26TuThT4/https
scp certs/client.crt certs/client.key certs/ca.crt pi@10.170.8.189:~/abcapsp26TuThT4/https/certs/
```

**Option B: Share with teammates (local dev)**

Give your teammates the three files:
- `client.crt`
- `client.key`
- `ca.crt`

They put them in `~/abcapsp26TuThT4/https/certs/` on their machine (or wherever the maze app expects them).

**Ways to share (pick one):**
- USB drive
- Secure file transfer (e.g. SCP from your machine to theirs)
- Encrypted messaging (e.g. password-protected zip)

**Do not** email or Slack the private key (`client.key`) in plain text.

---

## Step 4: Verify on Each Server

SSH into each server and check the certs are there:

```bash
ssh UNIQUE_LOGIN@10.170.8.130 "ls -la ~/abcapsp26TuThT4/https/certs/"
```

You should see: `server.crt`, `server.key`, `ca.crt`

---

## Step 5: Rebuild Servers on Remote Machines

SSH into each server, pull latest code, and rebuild:

```bash
ssh UNIQUE_LOGIN@10.170.8.130
cd ~/abcapsp26TuThT4
git pull
cd https
gcc -O2 -Wall -Wextra -std=c11 maze_https_mongo.c -o maze_https_mongo \
    $(pkg-config --cflags --libs libmicrohttpd libmongoc-1.0 gnutls)
# Then start: ./maze_https_mongo
```

Repeat for AI server (maze_https_redis) and MiniPupper (maze_https_telemetry).

---

## Checklist for Cert Coordinator

- [ ] Run `./gen_mtls_certs.sh` in https/certs/
- [ ] Copy server.crt, server.key, ca.crt to Logging Server (10.170.8.130)
- [ ] Copy server.crt, server.key, ca.crt to AI Server (10.170.8.109)
- [ ] Copy server.crt, server.key, ca.crt to MiniPupper (10.170.8.123)
- [ ] Copy client.crt, client.key, ca.crt to GameHat (10.170.8.189)
- [ ] Share client.crt, client.key, ca.crt with teammates for local dev

---

## For Teammates (Receiving Certs)

1. Get `client.crt`, `client.key`, `ca.crt` from the cert coordinator.
2. Put them in `~/abcapsp26TuThT4/https/certs/` on your machine.
3. Run the maze app from project root: `./maze/maze_sdl2_final_send`
