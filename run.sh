#!/bin/bash

# Script to run the Flask app

cd "$(dirname "$0")/backend"

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies if needed
if ! python -c "import flask" 2>/dev/null; then
    echo "📦 Installing Flask..."
    pip install flask flask-cors numpy matplotlib pydicom
fi

# Run the app
echo "🚀 Starting Flask app..."
echo "📍 Server will be available at: http://127.0.0.1:5001"
echo "   (Using port 5001 to avoid conflict with macOS AirPlay on port 5000)"
echo "🛑 Press Ctrl+C to stop"
echo ""
python app.py

