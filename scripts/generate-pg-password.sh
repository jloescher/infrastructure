#!/bin/bash
# Generate SCRAM-SHA-256 password hash for PostgreSQL
# Usage: ./scripts/generate-pg-password.sh

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <password>"
    echo "Generates SCRAM-SHA-256 hash for PostgreSQL userlist"
    exit 1
fi

PASSWORD="$1"

# Use openssl to generate the hash
# This mimics PostgreSQL's SCRAM-SHA-256 format
SALT=$(openssl rand -base64 16 | tr -d '/+=' | head -c 16)
ITERATIONS=4096

# Generate using Python (requires passlib)
python3 << EOF
import hashlib
import base64
import os
import hmac

password = "${PASSWORD}"
salt = "${SALT}"
iterations = ${ITERATIONS}

# Generate client key and server key
salt_bytes = salt.encode('utf-8')
salted_password = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_bytes, iterations)
client_key = hmac.new(salted_password, b"Client Key", hashlib.sha256).digest()
server_key = hmac.new(salted_password, b"Server Key", hashlib.sha256).digest()

stored_key = hashlib.sha256(client_key).digest()

# Format as SCRAM-SHA-256
print(f"SCRAM-SHA-256\${iterations}:{salt}\${base64.b64encode(stored_key).decode()}:{base64.b64encode(server_key).decode()}")
EOF