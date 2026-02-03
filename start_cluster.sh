#!/bin/bash
# Start OCR Cluster with configurable number of workers
# Usage: ./start_cluster.sh [OPTIONS]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuración por defecto
NUM_WORKERS=${NUM_WORKERS:-2}
BASE_PORT=5556

# Mostrar ayuda
show_help() {
    cat << EOF
╔══════════════════════════════════════════════════════════════╗
║              OCR Cluster - Script de Inicio                  ║
╚══════════════════════════════════════════════════════════════╝

Uso: ./start_cluster.sh [OPCIONES]

Opciones:
  -w, --workers N    Número de workers a iniciar (1-8)
                     Por defecto: 2 workers
  
  -h, --help         Mostrar esta ayuda

Ejemplos:
  ./start_cluster.sh              # Inicia 2 workers (por defecto)
  ./start_cluster.sh -w 1         # Inicia 1 worker
  ./start_cluster.sh -w 4         # Inicia 4 workers
  NUM_WORKERS=3 ./start_cluster.sh  # Variable de entorno

Puertos utilizados:
  - Balanceador/Frontend: 5555
  - Workers: 5556, 5557, 5558... (según NUM_WORKERS)

Memoria estimada por worker: ~2.5 GB RAM
  - 1 worker:  ~2.5 GB
  - 2 workers: ~5 GB
  - 4 workers: ~10 GB
  - 8 workers: ~20 GB

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
            if [[ ! "$NUM_WORKERS" =~ ^[1-8]$ ]]; then
                echo "❌ Error: El número de workers debe ser entre 1 y 8"
                exit 1
            fi
            shift 2
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
for i in $(seq 0 8); do
    PORT=$((5555 + i))
    lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
done
sleep 2

# Crear directorio de logs
mkdir -p logs

# Array para guardar PIDs
declare -a WORKER_PIDS

# Iniciar workers dinámicamente
for i in $(seq 1 $NUM_WORKERS); do
    WORKER_PORT=$((BASE_PORT + i - 1))
    echo "🔄 Iniciando Worker $i (puerto $WORKER_PORT)..."
    PYTHONUNBUFFERED=1 WORKER_ID="worker-$i" PORT=$WORKER_PORT python -u worker.py > logs/worker$i.log 2>&1 &
    WORKER_PID=$!
    echo "   PID: $WORKER_PID"
    echo "$WORKER_PID" > logs/worker$i.pid
    WORKER_PIDS+=($WORKER_PID)
done

# Esperar a que los modelos se carguen
echo ""
echo "⏳ Esperando a que los workers carguen PP-FormulaNet..."
echo "   (Esto puede tardar 30-60 segundos la primera vez)"
echo ""

# Mostrar progreso
for attempt in {1..120}; do
    # Verificar si todos los workers siguen vivos
    ALL_ALIVE=true
    for i in $(seq 1 $NUM_WORKERS); do
        PID=${WORKER_PIDS[$((i-1))]}
        if ! kill -0 $PID 2>/dev/null; then
            echo ""
            echo "❌ Worker $i falló. Ver logs/worker$i.log"
            exit 1
        fi
    done
    
    # Verificar si están listos
    READY_COUNT=0
    for i in $(seq 1 $NUM_WORKERS); do
        WORKER_PORT=$((BASE_PORT + i - 1))
        if curl -s http://localhost:$WORKER_PORT/status 2>/dev/null | grep -q '"ready": true'; then
            READY_COUNT=$((READY_COUNT + 1))
        fi
    done
    
    if [ "$READY_COUNT" -eq "$NUM_WORKERS" ]; then
        echo ""
        echo "✅ Todos los workers listos! ($READY_COUNT/$NUM_WORKERS)"
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
NUM_WORKERS=$NUM_WORKERS python balancer.py
