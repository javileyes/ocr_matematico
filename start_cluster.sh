#!/bin/bash
# Start OCR Cluster with configurable number of workers
# Usage: ./start_cluster.sh [OPTIONS]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuración por defecto
NUM_WORKERS=2

# Mostrar ayuda
show_help() {
    cat << EOF
╔══════════════════════════════════════════════════════════════╗
║              OCR Cluster - Script de Inicio                  ║
╚══════════════════════════════════════════════════════════════╝

Uso: ./start_cluster.sh [OPCIONES]

Opciones:
  -w, --workers N    Número de workers a iniciar (1 o 2)
                     Por defecto: 2 workers
  
  -2, --dual         Atajo para iniciar 2 workers (equivale a -w 2)
  
  -h, --help         Mostrar esta ayuda

Ejemplos:
  ./start_cluster.sh              # Inicia 1 worker (modo normal)
  ./start_cluster.sh -2           # Inicia 2 workers (modo dual)
  ./start_cluster.sh --workers 2  # Inicia 2 workers
  ./start_cluster.sh --dual       # Inicia 2 workers

Puertos utilizados:
  - Balanceador/Frontend: 5555
  - Worker 1: 5556
  - Worker 2: 5557 (solo con -2 o -w 2)

Memoria estimada:
  - 1 worker: ~4.5 GB RAM
  - 2 workers: ~9 GB RAM

Detener el cluster:
  ./stop_cluster.sh

EOF
}

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -w|--workers)
            NUM_WORKERS="$2"
            if [[ ! "$NUM_WORKERS" =~ ^[12]$ ]]; then
                echo "❌ Error: El número de workers debe ser 1 o 2"
                exit 1
            fi
            shift 2
            ;;
        -2|--dual)
            NUM_WORKERS=2
            shift
            ;;
        *)
            echo "❌ Opción desconocida: $1"
            echo "   Usa --help para ver las opciones disponibles"
            exit 1
            ;;
    esac
done

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         🚀 Starting OCR Cluster ($NUM_WORKERS worker(s))                 ║"
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
PYTHONUNBUFFERED=1 WORKER_ID="worker-1" PORT=5556 python -u worker.py > logs/worker1.log 2>&1 &
WORKER1_PID=$!
echo "   PID: $WORKER1_PID"
echo "$WORKER1_PID" > logs/worker1.pid

# Iniciar Worker 2 si se solicitaron 2 workers
if [ "$NUM_WORKERS" -eq 2 ]; then
    echo "🔄 Iniciando Worker 2 (puerto 5557)..."
    PYTHONUNBUFFERED=1 WORKER_ID="worker-2" PORT=5557 python -u worker.py > logs/worker2.log 2>&1 &
    WORKER2_PID=$!
    echo "   PID: $WORKER2_PID"
    echo "$WORKER2_PID" > logs/worker2.pid
fi

# Esperar a que los modelos se carguen
echo ""
echo "⏳ Esperando a que los workers carguen PaddleOCR-VL..."
echo "   (Esto puede tardar 30-60 segundos la primera vez)"
echo ""

# Mostrar progreso
for i in {1..90}; do
    # Verificar si los workers siguen vivos
    if ! kill -0 $WORKER1_PID 2>/dev/null; then
        echo ""
        echo "❌ Worker 1 falló. Ver logs/worker1.log"
        exit 1
    fi
    
    if [ "$NUM_WORKERS" -eq 2 ]; then
        if ! kill -0 $WORKER2_PID 2>/dev/null; then
            echo ""
            echo "❌ Worker 2 falló. Ver logs/worker2.log"
            exit 1
        fi
    fi
    
    # Verificar si están listos
    W1_READY=$(curl -s http://localhost:5556/status 2>/dev/null | grep -o '"ready": true' || echo "")
    
    if [ "$NUM_WORKERS" -eq 1 ]; then
        if [ -n "$W1_READY" ]; then
            echo ""
            echo "✅ Worker 1 listo!"
            break
        fi
    else
        W2_READY=$(curl -s http://localhost:5557/status 2>/dev/null | grep -o '"ready": true' || echo "")
        if [ -n "$W1_READY" ] && [ -n "$W2_READY" ]; then
            echo ""
            echo "✅ Ambos workers listos!"
            break
        fi
    fi
    
    echo -n "."
    sleep 1
done

# Configurar balanceador según número de workers
if [ "$NUM_WORKERS" -eq 1 ]; then
    export WORKERS_CONFIG="single"
else
    export WORKERS_CONFIG="dual"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           🔀 Iniciando Load Balancer                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Iniciar balanceador (en primer plano para ver los logs)
NUM_WORKERS=$NUM_WORKERS python balancer.py
