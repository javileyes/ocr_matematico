#!/bin/bash
# Stop OCR Cluster - Gracefully stop all processes
# Usage: ./stop_cluster.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Deteniendo OCR Cluster..."

# Detener por PID si existen los archivos
if [ -f logs/worker1.pid ]; then
    PID=$(cat logs/worker1.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "   Deteniendo Worker 1 (PID: $PID)..."
        kill $PID 2>/dev/null || true
    fi
    rm -f logs/worker1.pid
fi

if [ -f logs/worker2.pid ]; then
    PID=$(cat logs/worker2.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "   Deteniendo Worker 2 (PID: $PID)..."
        kill $PID 2>/dev/null || true
    fi
    rm -f logs/worker2.pid
fi

# Matar por puerto como fallback
echo "🧹 Limpiando puertos..."
lsof -ti :5555 | xargs kill -9 2>/dev/null || true
lsof -ti :5556 | xargs kill -9 2>/dev/null || true
lsof -ti :5557 | xargs kill -9 2>/dev/null || true

echo "✅ Cluster detenido"
