#!/bin/bash
set -e

echo "=== Starting NissiGrid Document Intelligence Platform ==="

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL database at ${DB_HOST:-db}:${DB_PORT:-5432}..."
python3 - << 'PYEOF'
import os, sys, time, psycopg2

host = os.environ.get("DB_HOST", "db")
port = os.environ.get("DB_PORT", "5432")
dbname = os.environ.get("DB_NAME", "scanner")
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "postgres")

max_retries = 30
for i in range(max_retries):
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=3)
        conn.close()
        print(f"Connected successfully to PostgreSQL ({dbname} at {host}:{port})")
        sys.exit(0)
    except Exception as e:
        print(f"Postgres not ready yet ({i+1}/{max_retries}): {e}")
        time.sleep(2)

print("Failed to connect to PostgreSQL after multiple retries.")
sys.exit(1)
PYEOF

# Ensure Database Tables Exist
echo "Verifying database schema..."
python3 - << 'PYEOF'
import os, psycopg2

host = os.environ.get("DB_HOST", "db")
port = os.environ.get("DB_PORT", "5432")
dbname = os.environ.get("DB_NAME", "scanner")
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "postgres")

conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
cur = conn.cursor()
cur.execute("SELECT to_regclass('public.billing_documents');")
exists = cur.fetchone()[0]

if not exists:
    print("Initializing database schema from app/persistence/schema.sql...")
    schema_path = "/app/app/persistence/schema.sql"
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        cur.execute(sql)
        conn.commit()
        print("Database schema successfully initialized!")
else:
    print("Database tables already exist. Ready.")

cur.close()
conn.close()
PYEOF

# Create necessary directories
mkdir -p /app/input_files /app/app/db

# Start Express API Server & Web UI
echo "Starting Node.js Server on port ${PORT:-5001}..."
cd /app/server
exec node server.js
