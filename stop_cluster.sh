#!/bin/bash
# Stop OCR Cluster - Gracefully stop all processes
# Usage: ./stop_cluster.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Deteniendo OCR Cluster..."

# Detener todos los workers por PID (buscar todos los archivos .pid)
for pidfile in logs/worker*.pid; do
    if [ -f "$pidfile" ]; then
        WORKER_NUM=$(echo "$pidfile" | grep -o '[0-9]*')
        PID=$(cat "$pidfile")
        if kill -0 $PID 2>/dev/null; then
            echo "   Deteniendo Worker $WORKER_NUM (PID: $PID)..."
            kill $PID 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
done

# Matar por puerto como fallback (puertos 5555-5563 para hasta 8 workers)
echo "🧹 Limpiando puertos..."
for PORT in $(seq 5555 5563); do
    lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
done

echo "✅ Cluster detenido"
