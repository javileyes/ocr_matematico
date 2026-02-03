"""
Math Formula OCR Web Application
Flask server with PaddleOCR VL for handwriting recognition
"""
import os
import io
import json
import uuid
import base64
import shutil
import tempfile
import threading
from pathlib import Path

from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from PIL import Image

# Suprimir verificación de conectividad de modelos
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# Importar PaddleOCR VL (modelo Vision-Language para fórmulas matemáticas)
PADDLE_AVAILABLE = False
pipeline = None

try:
    from paddleocr import PaddleOCRVL
    PADDLE_AVAILABLE = True
    print("✅ PaddleOCRVL importado correctamente")
except ImportError as e:
    print(f"⚠️  PaddleOCRVL no está instalado: {e}")
    print("   Usando modo demo.")

app = Flask(__name__)

# Configuración
USE_LAYOUT = os.getenv("USE_LAYOUT_DETECTION", "true").lower() == "true"
PORT = int(os.getenv("PORT", 8000))

# Lock para thread safety
_pipeline_lock = threading.Lock()

# Inicializar OCR VL al arrancar
if PADDLE_AVAILABLE:
    try:
        print("🔄 Cargando modelo PaddleOCR VL (esto puede tardar la primera vez)...")
        pipeline = PaddleOCRVL(use_layout_detection=USE_LAYOUT)
        print("✅ PaddleOCR VL cargado correctamente")
    except Exception as e:
        print(f"⚠️  Error al cargar PaddleOCR VL: {e}")
        PADDLE_AVAILABLE = False
        pipeline = None

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".pdf"}


def _ext_ok(path: str) -> bool:
    return Path(path).suffix.lower() in ALLOWED_EXT


def run_ocr(image_path: str):
    """Ejecuta OCR VL sobre una imagen y retorna el texto/LaTeX reconocido."""
    if not PADDLE_AVAILABLE or pipeline is None:
        return {
            "text": r"\int_{0}^{\infty} e^{-x^2} dx = \frac{\sqrt{\pi}}{2}",
            "demo_mode": True
        }
    
    if not _ext_ok(image_path):
        raise ValueError("Formato no soportado.")
    
    # Carpeta temporal para resultados
    outdir = Path(tempfile.mkdtemp(prefix="ocrvl_"))
    results_text = []

    with _pipeline_lock:
        output = pipeline.predict(image_path)
        print(f"[DEBUG] output type: {type(output)}")
        
        # Guardar a disco con la API oficial
        for res in output:
            print(f"[DEBUG] res type: {type(res)}")
            print(f"[DEBUG] res: {res}")
            res.save_to_json(save_path=str(outdir))

    # Recoger los JSON generados y extraer texto
    for jf in sorted(outdir.glob("*.json")):
        print(f"[DEBUG] Leyendo JSON: {jf}")
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[DEBUG] JSON data keys: {data.keys() if isinstance(data, dict) else 'not a dict'}")
            
            # PaddleOCRVL guarda el texto en parsing_res_list[].block_content
            if isinstance(data, dict) and "parsing_res_list" in data:
                for block in data["parsing_res_list"]:
                    if isinstance(block, dict) and "block_content" in block:
                        content = block["block_content"].strip()
                        if content:
                            results_text.append(content)
                            print(f"[DEBUG] Found block_content: {content}")

    # Limpiar
    shutil.rmtree(outdir, ignore_errors=True)

    full_text = " ".join(str(t) for t in results_text) if results_text else ""
    
    # Eliminar delimitadores $ del LaTeX (MathJax usa \[ \])
    full_text = full_text.strip()
    if full_text.startswith("$$") and full_text.endswith("$$"):
        full_text = full_text[2:-2].strip()
    elif full_text.startswith("$") and full_text.endswith("$"):
        full_text = full_text[1:-1].strip()
    
    print(f"[DEBUG] Texto final: {full_text}")
    
    return {
        "text": full_text,
        "demo_mode": False
    }


@app.route("/")
def index():
    """Página principal con el canvas para dibujar fórmulas."""
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    """Endpoint de health check."""
    return jsonify({
        "status": "ok",
        "paddle_available": PADDLE_AVAILABLE,
        "model": "PaddleOCRVL",
        "use_layout_detection": USE_LAYOUT
    })


@app.route("/predict", methods=["POST"])
def predict():
    """Recibe una imagen (base64 o file upload) y retorna el texto reconocido."""
    tmp_path = None
    try:
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
                return jsonify({"ok": False, "error": "No se encontró 'image' en el JSON"}), 400
        
        elif "file" in request.files:
            f = request.files["file"]
            filename = secure_filename(f.filename or f"upload-{uuid.uuid4().hex}")
            suffix = Path(filename).suffix or ".png"
            if suffix.lower() not in ALLOWED_EXT:
                return jsonify({"ok": False, "error": "Extensión no soportada"}), 400
            
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            f.save(tmp.name)
            tmp_path = tmp.name
        else:
            return jsonify({"ok": False, "error": "Envía 'image' (base64) o 'file'"}), 400

        result = run_ocr(tmp_path)
        
        return jsonify({
            "ok": True,
            "latex": result["text"],
            "demo_mode": result.get("demo_mode", False)
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


if __name__ == "__main__":
    print(f"🚀 Iniciando servidor en http://localhost:{PORT}")
    print(f"   PaddleOCR VL disponible: {PADDLE_AVAILABLE}")
    print(f"   Detección de layout: {USE_LAYOUT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
