# mTLS Certificate Setup Guide (Team4TT)

This guide explains how to correctly set up **mutual TLS (mTLS)** certificates for the project.

**Critical:**  
The AI server holds the **authoritative** CA and certificates.  
**All team members must use exactly these files.** Do **NOT** generate new certificates locally.

## 1. Required Certificate Files

These are the correct, authoritative files stored on the AI server:

- `ca.crt`          – CA certificate (public)  
- `ca.key`          – CA private key  
- `client.crt`      – Client certificate  
- `client.key`      – Client private key  
- `server.crt`      – Server certificate  
- `server.key`      – Server private key  
- `client.cnf`      – Client OpenSSL config  
- `server.cnf`      – Server OpenSSL config  
- `client.csr`      – Client certificate signing request  
- `server.csr`      – Server certificate signing request  
- `ca.srl`          – CA serial file  

All developers must have **identical** copies of these files.

## 2. NEVER Run `gen_mtls_certs.sh` Locally

Running the script will:

- Create a **new CA**
- Generate new client & server certificates
- Make your setup **incompatible** with the AI server
- Break mTLS authentication completely

**Safety step (strongly recommended):**

```bash
mv gen_mtls_certs.sh DO_NOT_RUN_gen_mtls_certs.sh
```

## 3. Download the Official Certificate Bundle

AI server details:

- **Host:** `10.170.8.109`  
- **Path:** `/home/team4tt/abcapsp26TuThT4/https/certs`  
- **File:** `certs_bundle.tar.gz`

From your **local machine**, run:

```bash
scp unique_login@10.170.8.109:/home/team4tt/abcapsp26TuThT4/https/certs/certs_bundle.tar.gz .
```

Enter your unique login and password when prompted.

## 4. Install Certificates on Your Machine

```bash
# Navigate to your local certs folder
cd ~/abcapsp26TuThT4/https/certs

# Remove any old / wrong / self-generated files
rm -f ca.* client.* server.* *.csr *.srl

# Extract the correct bundle (adjust path if you saved it elsewhere)
tar -xzvf ~/certs_bundle.tar.gz
```

## 5. Verify Everything Looks Correct

```bash
ls -l
```

Expected files:

```text
ca.crt
ca.key
ca.srl
client.crt
client.key
client.csr
client.cnf
server.crt
server.key
server.csr
server.cnf
DO_NOT_RUN_gen_mtls_certs.sh
```

If the list matches (or is very similar), you're good.
