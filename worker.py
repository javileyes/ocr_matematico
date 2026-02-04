"""
OCR Worker - PP-FormulaNet Formula Recognition
Part of the load-balanced cluster system
Uses FormulaRecognitionPipeline for better nested formula recognition
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
from typing import Union

import numpy as np
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image

# Configurar fuente de modelos PaddleX
os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", os.getenv("PADDLE_PDX_MODEL_SOURCE", "huggingface"))
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# Importar FormulaRecognitionPipeline
PADDLE_AVAILABLE = False
pipeline = None

try:
    from paddleocr import FormulaRecognitionPipeline
    PADDLE_AVAILABLE = True
    print("✅ FormulaRecognitionPipeline importado correctamente")
except ImportError as e:
    print(f"⚠️  FormulaRecognitionPipeline no está instalado: {e}")
    # Fallback a PaddleOCRVL si no está disponible
    try:
        from paddleocr import PaddleOCRVL
        PADDLE_AVAILABLE = True
        print("✅ Fallback a PaddleOCRVL")
    except ImportError as e2:
        print(f"⚠️  Tampoco está PaddleOCRVL: {e2}")

app = Flask(__name__)

# Configuración
FORMULA_MODEL = os.getenv("FORMULA_MODEL_NAME", "PP-FormulaNet_plus-L")
PORT = int(os.getenv("PORT", 5556))
WORKER_ID = os.getenv("WORKER_ID", f"worker-{PORT}")
DEVICE = os.getenv("PADDLE_DEVICE", "cpu")

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

# Inicializar pipeline al arrancar
if PADDLE_AVAILABLE:
    try:
        print(f"🔄 [{WORKER_ID}] Cargando modelo {FORMULA_MODEL}...")
        print(f"   Device: {DEVICE}")
        
        # Intentar usar FormulaRecognitionPipeline
        try:
            pipeline = FormulaRecognitionPipeline(
                device=DEVICE,
                formula_recognition_model_name=FORMULA_MODEL,
            )
            print(f"✅ [{WORKER_ID}] FormulaRecognitionPipeline con {FORMULA_MODEL} cargado")
        except NameError:
            # Fallback a PaddleOCRVL si FormulaRecognitionPipeline no existe
            pipeline = PaddleOCRVL(use_layout_detection=False)
            print(f"✅ [{WORKER_ID}] Fallback: PaddleOCRVL cargado")
            
    except Exception as e:
        print(f"⚠️  [{WORKER_ID}] Error al cargar pipeline: {e}")
        import traceback
        traceback.print_exc()
        PADDLE_AVAILABLE = False
        pipeline = None

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".pdf"}


def _ext_ok(path: str) -> bool:
    return Path(path).suffix.lower() in ALLOWED_EXT


def _decode_image(payload: Union[str, bytes]) -> np.ndarray:
    """
    Decodifica imagen desde bytes o base64.
    Devuelve numpy.ndarray RGB (H,W,3) uint8.
    """
    if isinstance(payload, str):
        s = payload.strip()
        if s.startswith("data:"):
            s = s.split(",", 1)[1]
        raw = base64.b64decode(s)
    else:
        raw = payload

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(img, dtype=np.uint8)


def latex_to_plain_math(latex: str) -> str:
    """Convierte LaTeX a formato matemático plano."""
    if not latex:
        return ""
    
    result = latex
    
    # Función auxiliar para encontrar el contenido entre llaves balanceadas
    def find_balanced_braces(s: str, start: int) -> tuple:
        """Encuentra el contenido entre {} balanceadas, retorna (contenido, pos_final)."""
        if start >= len(s) or s[start] != '{':
            return None, start
        
        depth = 0
        content_start = start + 1
        i = start
        while i < len(s):
            if s[i] == '{':
                depth += 1
            elif s[i] == '}':
                depth -= 1
                if depth == 0:
                    return s[content_start:i], i + 1
            i += 1
        return None, start
    
    # Función para procesar \frac con anidamiento
    def process_frac(s: str) -> str:
        while '\\frac' in s:
            idx = s.find('\\frac')
            # Buscar primer argumento
            pos = idx + 5
            while pos < len(s) and s[pos] in ' \t':
                pos += 1
            arg1, pos = find_balanced_braces(s, pos)
            if arg1 is None:
                break
            # Buscar segundo argumento
            while pos < len(s) and s[pos] in ' \t':
                pos += 1
            arg2, end_pos = find_balanced_braces(s, pos)
            if arg2 is None:
                break
            # Procesar recursivamente los argumentos
            arg1 = process_frac(arg1)
            arg2 = process_frac(arg2)
            # Reemplazar
            s = s[:idx] + f'({arg1})/({arg2})' + s[end_pos:]
        return s
    
    # Función para procesar \sqrt con anidamiento
    def process_sqrt(s: str) -> str:
        while '\\sqrt' in s:
            idx = s.find('\\sqrt')
            pos = idx + 5
            # Verificar si tiene índice opcional [n]
            while pos < len(s) and s[pos] in ' \t':
                pos += 1
            index = None
            if pos < len(s) and s[pos] == '[':
                bracket_end = s.find(']', pos)
                if bracket_end != -1:
                    index = s[pos+1:bracket_end]
                    pos = bracket_end + 1
            while pos < len(s) and s[pos] in ' \t':
                pos += 1
            arg, end_pos = find_balanced_braces(s, pos)
            if arg is None:
                break
            # Procesar recursivamente el argumento
            arg = process_sqrt(arg)
            arg = process_frac(arg)
            if index:
                s = s[:idx] + f'root({arg},{index})' + s[end_pos:]
            else:
                s = s[:idx] + f'sqrt({arg})' + s[end_pos:]
        return s
    
    # Procesar fracciones y raíces primero (son las más complejas)
    result = process_frac(result)
    result = process_sqrt(result)
    
    # Procesar potencias y subíndices con llaves
    def process_power_subscript(s: str, cmd: str, replacement: str) -> str:
        while cmd + '{' in s:
            idx = s.find(cmd + '{')
            pos = idx + len(cmd)
            arg, end_pos = find_balanced_braces(s, pos)
            if arg is None:
                break
            s = s[:idx] + replacement + '(' + arg + ')' + s[end_pos:]
        return s
    
    result = process_power_subscript(result, '^', '^')
    result = process_power_subscript(result, '_', '_')
    
    # Operadores
    result = re.sub(r'\\cdot', '*', result)
    result = re.sub(r'\\times', '*', result)
    result = re.sub(r'\\div', '/', result)
    result = re.sub(r'\\pm', '±', result)
    result = re.sub(r'\\mp', '∓', result)
    
    # Comparadores
    result = re.sub(r'\\leq', '≤', result)
    result = re.sub(r'\\geq', '≥', result)
    result = re.sub(r'\\neq', '≠', result)
    result = re.sub(r'\\le(?![a-z])', '≤', result)
    result = re.sub(r'\\ge(?![a-z])', '≥', result)
    
    # Símbolos griegos y especiales
    result = re.sub(r'\\pi(?![a-z])', 'π', result)
    result = re.sub(r'\\infty', '∞', result)
    result = re.sub(r'\\alpha', 'α', result)
    result = re.sub(r'\\beta', 'β', result)
    result = re.sub(r'\\gamma', 'γ', result)
    result = re.sub(r'\\theta', 'θ', result)
    result = re.sub(r'\\lambda', 'λ', result)
    result = re.sub(r'\\sigma', 'σ', result)
    result = re.sub(r'\\delta', 'δ', result)
    result = re.sub(r'\\epsilon', 'ε', result)
    result = re.sub(r'\\phi', 'φ', result)
    result = re.sub(r'\\omega', 'ω', result)
    
    # Operadores grandes
    result = re.sub(r'\\sum', 'Σ', result)
    result = re.sub(r'\\prod', 'Π', result)
    result = re.sub(r'\\int', '∫', result)
    
    # Delimitadores
    result = re.sub(r'\\left\(', '(', result)
    result = re.sub(r'\\right\)', ')', result)
    result = re.sub(r'\\left\[', '[', result)
    result = re.sub(r'\\right\]', ']', result)
    result = re.sub(r'\\left\{', '{', result)
    result = re.sub(r'\\right\}', '}', result)
    result = re.sub(r'\\left\.', '', result)
    result = re.sub(r'\\right\.', '', result)
    result = re.sub(r'\\left\|', '|', result)
    result = re.sub(r'\\right\|', '|', result)
    
    # Limpiar comandos restantes
    result = re.sub(r'\\[a-zA-Z]+', '', result)
    
    # Limpiar llaves sueltas que quedaron
    result = result.replace('{', '').replace('}', '')
    
    # Simplificar paréntesis redundantes en casos simples
    # (x)/(y) donde x e y son simples -> x/y
    result = re.sub(r'\(([a-zA-Z0-9]+)\)/\(([a-zA-Z0-9]+)\)', r'\1/\2', result)
    
    # Limpiar espacios
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


def run_ocr_formula(image_input):
    """
    Ejecuta OCR de fórmulas usando FormulaRecognitionPipeline.
    
    Args:
        image_input: Path a imagen o numpy array RGB
    
    Returns:
        dict con 'text' (LaTeX) y 'demo_mode'
    """
    if not PADDLE_AVAILABLE or pipeline is None:
        return {
            "text": "x^2 + 2x + 1",
            "demo_mode": True
        }
    
    with _pipeline_lock:
        print(f"[{WORKER_ID}] Running formula OCR...")
        
        try:
            # Usar FormulaRecognitionPipeline
            # Desactivar layout y preprocesado para canvas individual
            output = pipeline.predict(
                image_input,
                use_layout_detection=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            
            # Obtener primer resultado
            try:
                res = next(iter(output))
            except StopIteration:
                print(f"[{WORKER_ID}] No results from pipeline")
                return {"text": "", "demo_mode": False}
            
            # Explorar la estructura del resultado
            print(f"[{WORKER_ID}] Result type: {type(res)}")
            print(f"[{WORKER_ID}] Result dir: {[a for a in dir(res) if not a.startswith('_')]}")
            
            # Intentar obtener datos de varias formas
            data = None
            
            # Forma 1: atributo json (puede ser dict o método)
            if hasattr(res, 'json'):
                json_attr = getattr(res, 'json')
                if callable(json_attr):
                    data = json_attr()
                else:
                    data = json_attr
                print(f"[{WORKER_ID}] json attr: {data}")
            
            # Forma 2: atributo res
            if hasattr(res, 'res'):
                res_attr = getattr(res, 'res')
                print(f"[{WORKER_ID}] res attr type: {type(res_attr)}")
                print(f"[{WORKER_ID}] res attr: {res_attr}")
                if isinstance(res_attr, dict):
                    data = res_attr
                elif isinstance(res_attr, list) and len(res_attr) > 0:
                    data = res_attr[0] if isinstance(res_attr[0], dict) else {"formula_res_list": res_attr}
            
            # Forma 3: convertir a dict directamente
            if data is None and hasattr(res, '__dict__'):
                data = res.__dict__
                print(f"[{WORKER_ID}] __dict__: {data}")
            
            if data is None:
                data = {}
            
            # Buscar la fórmula en diferentes estructuras
            latex = ""
            
            # Estructura 1: formula_res_list
            frl = data.get("formula_res_list") or []
            if frl:
                if isinstance(frl, list) and len(frl) > 0:
                    first_item = frl[0]
                    if isinstance(first_item, dict):
                        latex = first_item.get("rec_formula", "")
                    elif isinstance(first_item, str):
                        latex = first_item
                print(f"[{WORKER_ID}] Got from formula_res_list: {latex}")
            
            # Estructura 2: rec_formula directamente
            if not latex and "rec_formula" in data:
                latex = data.get("rec_formula", "")
                print(f"[{WORKER_ID}] Got from rec_formula: {latex}")
            
            # Estructura 3: res contiene la fórmula (estructura anidada de FormulaRecognitionPipeline)
            if not latex:
                res_data = data.get("res")
                if isinstance(res_data, str):
                    latex = res_data
                    print(f"[{WORKER_ID}] Got from res string: {latex}")
                elif isinstance(res_data, dict):
                    # Buscar en res.formula_res_list primero
                    inner_frl = res_data.get("formula_res_list") or []
                    if inner_frl and isinstance(inner_frl, list) and len(inner_frl) > 0:
                        first_item = inner_frl[0]
                        if isinstance(first_item, dict):
                            latex = first_item.get("rec_formula", "")
                        elif isinstance(first_item, str):
                            latex = first_item
                        print(f"[{WORKER_ID}] Got from res.formula_res_list: {latex}")
                    else:
                        # Fallback a rec_formula directo en res
                        latex = res_data.get("rec_formula", "") or res_data.get("formula", "")
                        if latex:
                            print(f"[{WORKER_ID}] Got from res dict: {latex}")
                elif isinstance(res_data, list) and len(res_data) > 0:
                    first = res_data[0]
                    if isinstance(first, str):
                        latex = first
                    elif isinstance(first, dict):
                        latex = first.get("rec_formula", "") or first.get("formula", "")
                    print(f"[{WORKER_ID}] Got from res list: {latex}")
            
            # Estructura 4: parsing_res_list (formato PaddleOCR-VL)
            if not latex and "parsing_res_list" in data:
                for block in data["parsing_res_list"]:
                    if isinstance(block, dict) and "block_content" in block:
                        content = block["block_content"].strip()
                        if content:
                            latex = content
                            print(f"[{WORKER_ID}] Got from parsing_res_list: {latex}")
                            break
            
            if latex:
                return {"text": _clean_latex(latex.strip()), "demo_mode": False}
            
            print(f"[{WORKER_ID}] Could not extract formula from data: {data}")
            return {"text": "", "demo_mode": False}
            
        except Exception as e:
            print(f"[{WORKER_ID}] Error in formula OCR: {e}")
            import traceback
            traceback.print_exc()
            return {"text": "", "demo_mode": False}


def _clean_latex(text: str) -> str:
    """Limpia delimitadores LaTeX del texto."""
    text = text.strip()
    
    # Eliminar delimitadores $$ o $
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    elif text.startswith("$"):
        text = text[1:].strip()
    if text.endswith("$"):
        text = text[:-1].strip()
    
    return text


# Legacy function for compatibility
def run_ocr(image_path: str):
    """Ejecuta OCR sobre una imagen (legacy, usa run_ocr_formula internamente)."""
    return run_ocr_formula(image_path)


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
            "uptime_seconds": round(uptime, 1),
            "model": FORMULA_MODEL
        })


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "worker_id": WORKER_ID,
        "ready": PADDLE_AVAILABLE and pipeline is not None
    })


@app.route("/predict", methods=["POST"])
def predict():
    """Endpoint principal de predicción."""
    if not PADDLE_AVAILABLE or pipeline is None:
        return jsonify({
            "ok": False,
            "error": "OCR no disponible"
        }), 503
    
    with _state_lock:
        if worker_state["busy"]:
            return jsonify({
                "ok": False,
                "error": "Worker ocupado"
            }), 503
        worker_state["busy"] = True
        worker_state["current_request"] = str(uuid.uuid4())[:8]
    
    try:
        data = request.get_json()
        print(f"[{WORKER_ID}] Received predict request, data keys: {data.keys() if data else 'None'}")
        
        if not data or "image" not in data:
            print(f"[{WORKER_ID}] No image in request")
            return jsonify({
                "ok": False,
                "error": "No se proporcionó imagen"
            }), 400
        
        # Decodificar imagen desde base64
        try:
            img_np = _decode_image(data["image"])
        except Exception as e:
            return jsonify({
                "ok": False,
                "error": f"Error al decodificar imagen: {e}"
            }), 400
        
        # Ejecutar OCR
        result = run_ocr_formula(img_np)
        
        with _state_lock:
            worker_state["requests_processed"] += 1
            worker_state["last_request_time"] = time.time()
        
        latex = result.get("text", "")
        
        return jsonify({
            "ok": True,
            "latex": latex,
            "plain_math": latex_to_plain_math(latex),
            "demo_mode": result.get("demo_mode", False),
            "worker_id": WORKER_ID
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
        
    finally:
        with _state_lock:
            worker_state["busy"] = False
            worker_state["current_request"] = None


if __name__ == "__main__":
    print(f"🚀 [{WORKER_ID}] Starting OCR Worker on port {PORT}...")
    print(f"   Model: {FORMULA_MODEL}")
    print(f"   Device: {DEVICE}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
