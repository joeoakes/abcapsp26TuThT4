# maze_https_mongo
**C HTTPS JSON → MongoDB Server**

This project is a secure (HTTPS/TLS) version of the original `maze_http_mongo` server.

It is a small **C** program that:

- Listens for **HTTPS** requests (TLS)
- Receives a **JSON document**
- Appends a server timestamp
- Inserts the document into **MongoDB**

---

## Endpoint

- **POST** `/move`
- **Content-Type:** `application/json`
- **Protocol:** HTTPS

The server automatically appends:

```json
"received_at": "YYYY-MM-DDTHH:MM:SSZ"
```

---

## Requirements

### Libraries
- `libmicrohttpd` (with TLS / GnuTLS support)
- MongoDB C Driver:
  - `libmongoc`
  - `libbson`
- `pkg-config`
- `gcc` or `clang`

### Debian / Ubuntu / Raspberry Pi OS

```bash
sudo apt update
sudo apt install -y   build-essential   pkg-config   libmicrohttpd-dev   libgnutls28-dev   libmongoc-dev   libbson-dev
```

---

## mTLS Certificates (Required)

The project uses **mutual TLS (mTLS)**: the server proves its identity, and the client (robot/GameHat) proves its identity. Generate all certificates with:

```bash
cd https/certs
./gen_mtls_certs.sh
```

This creates:

| File | Purpose |
|------|---------|
| `ca.crt` | CA certificate — server uses to verify clients; client uses to verify server |
| `server.crt` | Server certificate |
| `server.key` | Server private key |
| `client.crt` | Client certificate (robot/GameHat) |
| `client.key` | Client private key |

**Deploy:** Copy `server.crt`, `server.key`, and `ca.crt` to each HTTPS server. Copy `client.crt`, `client.key`, and `ca.crt` to each robot/GameHat client.

---

## Build

```bash
gcc -O2 -Wall -Wextra -std=c11 maze_https_mongo.c -o maze_https_mongo   $(pkg-config --cflags --libs libmicrohttpd libmongoc-1.0 gnutls)
```

---

## Run

### Default configuration

```bash
./maze_https_mongo
```

Defaults:
- **Port:** `8443`
- **Mongo URI:** `mongodb://localhost:27017`
- **Database:** `maze`
- **Collection:** `moves`
- **TLS Cert:** `certs/server.crt`
- **TLS Key:** `certs/server.key`

### Override using environment variables

```bash
LISTEN_PORT=9443 CERT_FILE=certs/server.crt KEY_FILE=certs/server.key MONGO_URI="mongodb://localhost:27017" MONGO_DB="maze" MONGO_COL="moves" ./maze_https_mongo
```

---

## Test with curl

With mTLS, provide client cert, key, and CA:

```bash
curl --cert certs/client.crt --key certs/client.key --cacert certs/ca.crt \
  -X POST https://localhost:8446/move -H "Content-Type: application/json" -d '{
    "event_type": "player_move",
    "input": {
      "device": "joystick",
      "move_sequence": 1
    },
    "player": {
      "position": { "x": 1, "y": 2 }
    },
    "goal_reached": false,
    "timestamp": "2026-01-25T11:42:18Z"
  }'
```

For servers using different hostnames (e.g. `10.170.8.101`), the server cert includes SANs for common lab IPs.

Expected response:

```json
{"status":"ok"}
```

---

## SDL / Game Client Notes

From an SDL or C-based client, HTTPS requests are commonly sent using **libcurl**.

The maze client uses mTLS: `CURLOPT_SSLCERT`, `CURLOPT_SSLKEY`, `CURLOPT_CAINFO`, with `CURLOPT_SSL_VERIFYPEER=1` and `CURLOPT_SSL_VERIFYHOST=2`. Override paths via `MTLS_CLIENT_CERT`, `MTLS_CLIENT_KEY`, `MTLS_CA_FILE`.

---

## Production Notes

For production deployments:

- Use a **CA-signed certificate** (Let’s Encrypt or internal CA)
- Enable TLS verification on clients
- Consider:
  - Mutual TLS (client certificates)
  - JWT or API key authentication
  - Running behind a reverse proxy (nginx)

---

## Summary

✔ mTLS (mutual TLS) — server and client both prove identity  
✔ Encrypted HTTPS transport  
✔ Same JSON payload as HTTP version  
✔ MongoDB ingestion unchanged  
✔ Ideal for labs, SDL games, and telemetry pipelines  
