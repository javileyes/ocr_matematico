"""
Load Balancer - Distributes OCR requests across worker instances
Provides frontend and intelligent routing with queue management
"""
import os
import time
import json
from collections import deque
from threading import Thread, Lock

from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

# Configuración
PORT = int(os.getenv("PORT", 5555))
NUM_WORKERS = int(os.getenv("NUM_WORKERS", 2))
BASE_WORKER_PORT = 5556

# Generar lista de workers dinámicamente
WORKERS = [
    {"url": f"http://localhost:{BASE_WORKER_PORT + i}", "id": f"worker-{i + 1}"}
    for i in range(NUM_WORKERS)
]

HEALTH_CHECK_INTERVAL = 5  # seconds
REQUEST_TIMEOUT = 120  # seconds for OCR

# Estado del balanceador
class LoadBalancer:
    def __init__(self, workers):
        self.workers = workers
        self.worker_status = {w["id"]: {"healthy": False, "busy": False, "last_check": 0} for w in workers}
        self.request_queue = deque()
        self.queue_lock = Lock()
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "requests_per_worker": {w["id"]: 0 for w in workers}
        }
        self._start_health_checker()
    
    def _start_health_checker(self):
        """Inicia el thread de health check."""
        def check_loop():
            while True:
                self._check_all_workers()
                time.sleep(HEALTH_CHECK_INTERVAL)
        
        thread = Thread(target=check_loop, daemon=True)
        thread.start()
        print("🔍 Health checker iniciado")
    
    def _check_all_workers(self):
        """Verifica el estado de todos los workers."""
        for worker in self.workers:
            try:
                resp = requests.get(f"{worker['url']}/status", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    self.worker_status[worker["id"]] = {
                        "healthy": data.get("ready", False),
                        "busy": data.get("busy", False),
                        "last_check": time.time(),
                        "requests_processed": data.get("requests_processed", 0)
                    }
                else:
                    self.worker_status[worker["id"]]["healthy"] = False
            except Exception as e:
                self.worker_status[worker["id"]]["healthy"] = False
                self.worker_status[worker["id"]]["busy"] = False
    
    def get_best_worker(self):
        """Selecciona el mejor worker disponible."""
        # Prioridad: worker libre y healthy
        available = []
        for worker in self.workers:
            status = self.worker_status[worker["id"]]
            if status["healthy"] and not status["busy"]:
                available.append(worker)
        
        if available:
            # Devolver el que haya procesado menos requests (balance)
            return min(available, key=lambda w: self.stats["requests_per_worker"].get(w["id"], 0))
        
        # Si todos están ocupados, seleccionar cualquier healthy
        healthy = [w for w in self.workers if self.worker_status[w["id"]]["healthy"]]
        if healthy:
            return min(healthy, key=lambda w: self.stats["requests_per_worker"].get(w["id"], 0))
        
        return None
    
    def forward_request(self, image_data):
        """Reenvía la petición al mejor worker disponible."""
        self.stats["total_requests"] += 1
        
        worker = self.get_best_worker()
        if not worker:
            self.stats["failed_requests"] += 1
            return {"ok": False, "error": "No hay workers disponibles"}, 503
        
        # Marcar como ocupado temporalmente
        self.worker_status[worker["id"]]["busy"] = True
        
        try:
            start_time = time.time()
            
            resp = requests.post(
                f"{worker['url']}/predict",
                json={"image": image_data},
                timeout=REQUEST_TIMEOUT
            )
            
            elapsed = round(time.time() - start_time, 2)
            
            if resp.status_code == 200:
                self.stats["successful_requests"] += 1
                self.stats["requests_per_worker"][worker["id"]] += 1
                
                result = resp.json()
                result["routed_to"] = worker["id"]
                result["balancer_time"] = elapsed
                return result, 200
            else:
                self.stats["failed_requests"] += 1
                return resp.json(), resp.status_code
                
        except requests.Timeout:
            self.stats["failed_requests"] += 1
            return {"ok": False, "error": f"Timeout al procesar en {worker['id']}"}, 504
        except Exception as e:
            self.stats["failed_requests"] += 1
            return {"ok": False, "error": str(e)}, 500
        finally:
            # Refrescar estado después de la petición
            self._check_worker(worker)
    
    def _check_worker(self, worker):
        """Verifica un worker específico."""
        try:
            resp = requests.get(f"{worker['url']}/status", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                self.worker_status[worker["id"]] = {
                    "healthy": data.get("ready", False),
                    "busy": data.get("busy", False),
                    "last_check": time.time(),
                    "requests_processed": data.get("requests_processed", 0)
                }
        except:
            pass
    
    def get_cluster_status(self):
        """Estado completo del cluster."""
        return {
            "workers": [
                {
                    "id": w["id"],
                    "url": w["url"],
                    **self.worker_status[w["id"]]
                }
                for w in self.workers
            ],
            "stats": self.stats,
            "healthy_workers": sum(1 for w in self.workers if self.worker_status[w["id"]]["healthy"]),
            "total_workers": len(self.workers)
        }


# Instancia global del balanceador
balancer = LoadBalancer(WORKERS)


@app.route("/")
def index():
    """Página principal con el canvas."""
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    """Health check del balanceador."""
    status = balancer.get_cluster_status()
    return jsonify({
        "status": "healthy" if status["healthy_workers"] > 0 else "unhealthy",
        "mode": "cluster",
        "healthy_workers": status["healthy_workers"],
        "total_workers": status["total_workers"]
    })


@app.route("/cluster/status", methods=["GET"])
def cluster_status():
    """Estado detallado del cluster."""
    return jsonify(balancer.get_cluster_status())


@app.route("/predict", methods=["POST"])
def predict():
    """Recibe petición y la enruta al mejor worker."""
    try:
        if request.is_json:
            data = request.json
            if "image" not in data:
                return jsonify({"ok": False, "error": "No 'image' in request"}), 400
            
            result, status_code = balancer.forward_request(data["image"])
            return jsonify(result), status_code
        else:
            return jsonify({"ok": False, "error": "JSON required"}), 400
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# Servir archivos estáticos
@app.route("/static/<path:filename>")
def static_files(filename):
    return app.send_static_file(filename)


if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║             🔀 OCR Load Balancer - Cluster Mode              ║
╠══════════════════════════════════════════════════════════════╣
║  Frontend:  http://localhost:{PORT}                            ║
║  Workers:   {', '.join(w['url'] for w in WORKERS)}       ║
║  Health:    http://localhost:{PORT}/health                     ║
║  Status:    http://localhost:{PORT}/cluster/status             ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Esperar a que los workers estén listos
    print("⏳ Esperando a que los workers estén listos...")
    ready_count = 0
    max_wait = 120
    start = time.time()
    
    while ready_count < len(WORKERS) and (time.time() - start) < max_wait:
        ready_count = sum(1 for w in WORKERS if balancer.worker_status[w["id"]]["healthy"])
        if ready_count < len(WORKERS):
            time.sleep(2)
            balancer._check_all_workers()
    
    if ready_count > 0:
        print(f"✅ {ready_count}/{len(WORKERS)} workers listos")
    else:
        print("⚠️  No hay workers disponibles, iniciando de todos modos...")
    
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
