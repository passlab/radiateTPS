#!/bin/bash

# Script to stop the Flask app

echo "🛑 Stopping Flask app..."

# Kill processes running app.py
pkill -f "python.*app.py" 2>/dev/null

# Kill processes on port 5000
PID=$(lsof -ti:5000 2>/dev/null)
if [ ! -z "$PID" ]; then
    kill -9 $PID 2>/dev/null
    echo "✅ Stopped process on port 5000"
else
    echo "ℹ️  No Flask app running on port 5000"
fi

sleep 1

# Verify
if lsof -ti:5000 >/dev/null 2>&1; then
    echo "⚠️  Port 5000 still in use. Try: kill -9 \$(lsof -ti:5000)"
else
    echo "✅ Flask app stopped successfully"
fi

