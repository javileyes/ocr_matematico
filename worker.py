"""
OCR Worker - Standalone PaddleOCR-VL Instance
Part of the load-balanced cluster system
"""
import os
import io
import re
import json
import uuid
import base64
import shutil
import tempfile
import threading
import time
from pathlib import Path

from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image

# Suprimir verificación de conectividad de modelos
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# Importar PaddleOCR VL
PADDLE_AVAILABLE = False
pipeline = None

try:
    from paddleocr import PaddleOCRVL
    PADDLE_AVAILABLE = True
    print("✅ PaddleOCRVL importado correctamente")
except ImportError as e:
    print(f"⚠️  PaddleOCRVL no está instalado: {e}")

app = Flask(__name__)

# Configuración
USE_LAYOUT = os.getenv("USE_LAYOUT_DETECTION", "true").lower() == "true"
PORT = int(os.getenv("PORT", 5556))
WORKER_ID = os.getenv("WORKER_ID", f"worker-{PORT}")

# Estado del worker
worker_state = {
    "busy": False,
    "current_request": None,
    "requests_processed": 0,
    "last_request_time": None,
    "start_time": time.time()
}
_state_lock = threading.Lock()
_pipeline_lock = threading.Lock()

# Inicializar OCR VL al arrancar
if PADDLE_AVAILABLE:
    try:
        print(f"🔄 [{WORKER_ID}] Cargando modelo PaddleOCR VL...")
        pipeline = PaddleOCRVL(use_layout_detection=USE_LAYOUT)
        print(f"✅ [{WORKER_ID}] PaddleOCR VL cargado correctamente")
    except Exception as e:
        print(f"⚠️  [{WORKER_ID}] Error al cargar PaddleOCR VL: {e}")
        PADDLE_AVAILABLE = False
        pipeline = None

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".pdf"}


def _ext_ok(path: str) -> bool:
    return Path(path).suffix.lower() in ALLOWED_EXT


def latex_to_plain_math(latex: str) -> str:
    """Convierte LaTeX a formato matemático plano."""
    if not latex:
        return ""
    
    result = latex
    result = re.sub(r'\\frac\s*\{([^}]*)\}\s*\{([^}]*)\}', r'(\1)/(\2)', result)
    result = re.sub(r'\\sqrt\s*\{([^}]*)\}', r'sqrt(\1)', result)
    result = re.sub(r'\^{([^}]*)}', r'^(\1)', result)
    result = re.sub(r'_{([^}]*)}', r'_\1', result)
    
    for func in ['sin', 'cos', 'tan', 'log', 'ln', 'exp', 'lim']:
        result = re.sub(rf'\\{func}', func, result)
    
    result = result.replace('\\pi', 'pi')
    result = result.replace('\\infty', 'inf')
    result = re.sub(r'(\d)([a-zA-Z])', r'\1*\2', result)
    result = result.replace('\\,', '')
    result = result.replace('\\;', '')
    result = result.replace('\\ ', '')
    result = result.replace('\\quad', ' ')
    result = result.replace('{', '(')
    result = result.replace('}', ')')
    result = re.sub(r'\^\(([a-zA-Z0-9]+)\)', r'^\1', result)
    result = re.sub(r'_\(([a-zA-Z0-9]+)\)', r'_\1', result)
    result = re.sub(r'\(([a-zA-Z0-9]+)\)/\(([a-zA-Z0-9]+)\)', r'\1/\2', result)
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


def run_ocr(image_path: str):
    """Ejecuta OCR VL sobre una imagen."""
    if not PADDLE_AVAILABLE or pipeline is None:
        return {
            "text": "x^2 + 2x + 1",
            "demo_mode": True
        }
    
    # Carpeta temporal para resultados
    outdir = Path(tempfile.mkdtemp(prefix="ocrvl_"))
    results_text = []
    
    with _pipeline_lock:
        print(f"[{WORKER_ID}] Running OCR on {image_path}")
        output = pipeline.predict(image_path)
        
        # Guardar a disco con la API oficial
        for res in output:
            print(f"[{WORKER_ID}] Result type: {type(res)}")
            res.save_to_json(save_path=str(outdir))
    
    # Recoger los JSON generados y extraer texto
    for jf in sorted(outdir.glob("*.json")):
        print(f"[{WORKER_ID}] Reading JSON: {jf}")
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[{WORKER_ID}] JSON keys: {data.keys() if isinstance(data, dict) else 'not a dict'}")
            
            if isinstance(data, dict) and "parsing_res_list" in data:
                parsing_list = data["parsing_res_list"]
                print(f"[{WORKER_ID}] parsing_res_list has {len(parsing_list)} items")
                for block in parsing_list:
                    if isinstance(block, dict) and "block_content" in block:
                        content = block["block_content"].strip()
                        if content:
                            results_text.append(content)
                            print(f"[{WORKER_ID}] Found content: {content}")
    
    # Limpiar
    shutil.rmtree(outdir, ignore_errors=True)
    
    full_text = " ".join(str(t) for t in results_text) if results_text else ""
    full_text = full_text.strip()
    if full_text.startswith("$$") and full_text.endswith("$$"):
        full_text = full_text[2:-2].strip()
    elif full_text.startswith("$") and full_text.endswith("$"):
        full_text = full_text[1:-1].strip()
    
    print(f"[{WORKER_ID}] Final result: '{full_text}'")
    
    return {
        "text": full_text,
        "demo_mode": False
    }


@app.route("/status", methods=["GET"])
def status():
    """Estado actual del worker."""
    with _state_lock:
        uptime = time.time() - worker_state["start_time"]
        return jsonify({
            "worker_id": WORKER_ID,
            "ready": PADDLE_AVAILABLE and pipeline is not None,
            "busy": worker_state["busy"],
            "requests_processed": worker_state["requests_processed"],
            "uptime_seconds": round(uptime, 1)
        })


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy" if PADDLE_AVAILABLE else "degraded",
        "worker_id": WORKER_ID,
        "paddle_available": PADDLE_AVAILABLE
    })


@app.route("/predict", methods=["POST"])
def predict():
    """Procesa una petición de OCR."""
    request_id = str(uuid.uuid4())[:8]
    
    with _state_lock:
        worker_state["busy"] = True
        worker_state["current_request"] = request_id
    
    tmp_path = None
    try:
        start_time = time.time()
        
        if request.is_json:
            data = request.json
            if "image" in data:
                image_data = data["image"]
                if "," in image_data:
                    image_data = image_data.split(",")[1]
                
                image_bytes = base64.b64decode(image_data)
                
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                tmp.write(image_bytes)
                tmp.close()
                tmp_path = tmp.name
            else:
                return jsonify({"ok": False, "error": "No 'image' in JSON"}), 400
        
        elif "file" in request.files:
            f = request.files["file"]
            filename = secure_filename(f.filename or f"upload-{uuid.uuid4().hex}")
            suffix = Path(filename).suffix or ".png"
            if suffix.lower() not in ALLOWED_EXT:
                return jsonify({"ok": False, "error": "Unsupported extension"}), 400
            
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            f.save(tmp.name)
            tmp_path = tmp.name
        else:
            return jsonify({"ok": False, "error": "Send 'image' (base64) or 'file'"}), 400

        result = run_ocr(tmp_path)
        latex_text = result["text"]
        plain_math = latex_to_plain_math(latex_text)
        
        elapsed = round(time.time() - start_time, 2)
        print(f"[{WORKER_ID}] Request {request_id} completed in {elapsed}s")
        
        return jsonify({
            "ok": True,
            "latex": latex_text,
            "plain_math": plain_math,
            "demo_mode": result.get("demo_mode", False),
            "worker_id": WORKER_ID,
            "processing_time": elapsed
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
    
    finally:
        if tmp_path and Path(tmp_path).exists():
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        
        with _state_lock:
            worker_state["busy"] = False
            worker_state["current_request"] = None
            worker_state["requests_processed"] += 1
            worker_state["last_request_time"] = time.time()


if __name__ == "__main__":
    print(f"🚀 [{WORKER_ID}] Iniciando worker en http://localhost:{PORT}")
    print(f"   PaddleOCR VL disponible: {PADDLE_AVAILABLE}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
