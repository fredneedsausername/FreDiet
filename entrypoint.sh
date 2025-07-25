#!/bin/bash
set -e

echo "🚀 Starting Frediet application..."

# Initialize database if it doesn't exist
if [ ! -f "/app/data/frediet.db" ]; then
    echo "📊 Database not found. Initializing..."
    python init_db.py
fi

echo "✅ Starting web server..."
exec python server.py