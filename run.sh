#!/usr/bin/env bash
set -e

echo "[*] Starting backend..."
cd backend
source venv/bin/activate
nohup uvicorn src.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  > ../backend.log 2>&1 &
BACK_PID=$!

cd ..

echo "[*] Starting frontend..."
cd frontend
nohup npm run dev -- --host 0.0.0.0 --port 5173 \
  > ../frontend.log 2>&1 &
FRONT_PID=$!

cd ..

echo "[OK] Backend PID: $BACK_PID"
echo "[OK] Frontend PID: $FRONT_PID"
echo "[OK] Logs: backend.log / frontend.log"
