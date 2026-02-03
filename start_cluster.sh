#!/bin/bash
# Start OCR Cluster - 2 Workers + Load Balancer
# Usage: ./start_cluster.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           🚀 Starting OCR Cluster (2 Workers)                ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Matar procesos anteriores si existen
echo "🧹 Limpiando procesos anteriores..."
lsof -ti :5555 | xargs kill -9 2>/dev/null || true
lsof -ti :5556 | xargs kill -9 2>/dev/null || true
lsof -ti :5557 | xargs kill -9 2>/dev/null || true
sleep 2

# Crear directorio de logs
mkdir -p logs

# Iniciar Worker 1
echo "🔄 Iniciando Worker 1 (puerto 5556)..."
WORKER_ID="worker-1" PORT=5556 python worker.py > logs/worker1.log 2>&1 &
WORKER1_PID=$!
echo "   PID: $WORKER1_PID"

# Iniciar Worker 2
echo "🔄 Iniciando Worker 2 (puerto 5557)..."
WORKER_ID="worker-2" PORT=5557 python worker.py > logs/worker2.log 2>&1 &
WORKER2_PID=$!
echo "   PID: $WORKER2_PID"

# Guardar PIDs para poder detenerlos después
echo "$WORKER1_PID" > logs/worker1.pid
echo "$WORKER2_PID" > logs/worker2.pid

# Esperar a que los modelos se carguen
echo ""
echo "⏳ Esperando a que los workers carguen PaddleOCR-VL..."
echo "   (Esto puede tardar 30-60 segundos la primera vez)"
echo ""

# Mostrar progreso
for i in {1..60}; do
    # Verificar si los workers siguen vivos
    if ! kill -0 $WORKER1_PID 2>/dev/null; then
        echo ""
        echo "❌ Worker 1 falló. Ver logs/worker1.log"
        exit 1
    fi
    if ! kill -0 $WORKER2_PID 2>/dev/null; then
        echo ""
        echo "❌ Worker 2 falló. Ver logs/worker2.log"
        exit 1
    fi
    
    # Verificar si están listos
    W1_READY=$(curl -s http://localhost:5556/status 2>/dev/null | grep -o '"ready": true' || echo "")
    W2_READY=$(curl -s http://localhost:5557/status 2>/dev/null | grep -o '"ready": true' || echo "")
    
    if [ -n "$W1_READY" ] && [ -n "$W2_READY" ]; then
        echo ""
        echo "✅ Ambos workers listos!"
        break
    fi
    
    echo -n "."
    sleep 1
done

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           🔀 Iniciando Load Balancer                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Iniciar balanceador (en primer plano para ver los logs)
python balancer.py
