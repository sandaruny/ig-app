#!/bin/bash
# IG Trading Bot - Start Script
# Starts both backend and frontend dev servers

set -e

export PATH="/opt/homebrew/bin:$PATH"

echo "🚀 Starting IG Trading Bot..."

# Start backend
echo "Starting backend server on :8000..."
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Start frontend
echo "Starting frontend dev server on :5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "================================"
echo "  IG Trading Bot Running"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "================================"
echo ""
echo "Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
