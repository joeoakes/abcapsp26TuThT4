#!/usr/bin/env bash
# gen_mtls_certs.sh — Generate mTLS certificates (CA, server, client)
#
# Run (no build needed — it's a script):
#   cd ~/abcapsp26TuThT4/https/certs
#   ./gen_mtls_certs.sh
#
# Requires: openssl
# Output: ca.crt, server.crt, client.crt, etc. in the certs/ directory (same as script)

set -euo pipefail

cd "$(dirname "$0")"

echo "[1/6] Generating CA key..."
openssl genrsa -out ca.key 4096

echo "[2/6] Generating CA certificate..."
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650   -subj "/C=US/ST=PA/L=Langhorne/O=Demo CA/OU=Security/CN=Demo Root CA"   -out ca.crt

echo "[3/6] Generating server key..."
openssl genrsa -out server.key 2048

echo "[4/6] Generating server CSR..."
openssl req -new -key server.key -out server.csr -config server.cnf

echo "[5/6] Signing server certificate with CA (includes SAN)..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial   -out server.crt -days 825 -sha256 -extensions req_ext -extfile server.cnf

echo "[6/6] Generating client key + CSR + certificate..."
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr -config client.cnf
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial   -out client.crt -days 825 -sha256

echo
echo "Done. Generated certs:"
ls -1 ca.crt ca.key server.crt server.key client.crt client.key