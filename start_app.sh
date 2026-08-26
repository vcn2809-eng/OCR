#!/bin/bash
# NissiGrid Web Application Launcher Script

echo "=================================================="
echo "🚀 NissiGrid Document Intelligence System"
echo "=================================================="

# Check if PostgreSQL service is running
if ! psql -lqt | cut -d \| -f 1 | grep -qw scanner; then
  echo "⚠️ Warning: Database 'scanner' not found. Creating database..."
  createdb scanner 2>/dev/null || true
  psql -d scanner -f app/persistence/schema.sql 2>/dev/null || true
fi

# Ensure Python virtual environment exists
if [ -d ".venv" ]; then
  echo "🐍 Activating Python virtual environment..."
  source .venv/bin/activate
fi

# Start Express Backend API Server
echo "⚡ Starting Express API Server on port 5001..."
node server/server.js &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# Start React Frontend
echo "🌐 Starting React Web Application..."
cd frontend
npm run dev

# Kill backend process when frontend exits
kill $BACKEND_PID 2>/dev/null || true
