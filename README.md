# 🧮 OCR Matemático

Aplicación web para reconocimiento de fórmulas matemáticas escritas a mano. Dibuja una fórmula en el canvas, selecciona el área y obtén el código LaTeX correspondiente.

![Demo](https://img.shields.io/badge/Status-Working-green) ![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20Silicon-silver)

## ✨ Características

- 🖌️ **Canvas de dibujo** con soporte para mouse y touch
- 🔲 **Selección de área** para reconocimiento específico
- 🧠 **PP-FormulaNet_plus-L** - Modelo especializado en fórmulas matemáticas complejas
- 📐 **Salida LaTeX** con preview renderizado (MathJax)
- 🔢 **Formato plano** alternativo (sin comandos LaTeX)
- 🎨 **Interfaz moderna** con temas claro/oscuro y efectos glassmorphism
- ⚡ **Cluster de workers** con balanceo de carga

## 📋 Requisitos

- macOS con Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- ~4GB de espacio libre (modelos PaddleX)

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd ocr_matematico
```

### 2. Crear entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install --upgrade pip
pip install paddlepaddle
pip install "paddleocr[doc-parser]"
pip install Flask Pillow gunicorn requests numpy
```

> **Nota:** La primera vez, PaddleX descargará los modelos (~700MB para PP-FormulaNet_plus-L).

### 4. Verificar instalación

```bash
python -c "from paddleocr import FormulaRecognitionPipeline; print('✅ Pipeline instalado')"
```

## ▶️ Ejecución

### Modo Cluster (Recomendado)

```bash
# Iniciar cluster con 2 workers
./start_cluster.sh

# Detener cluster
./stop_cluster.sh
```

Abre en el navegador: **http://localhost:5555**

### Modo desarrollo simple

```bash
python app.py
```

## 🎯 Uso

1. **Dibuja** una fórmula matemática en el canvas
2. Haz clic en **"Seleccionar"** (ícono de cuadrado)
3. **Arrastra** para seleccionar el área de la fórmula
4. Haz clic en **"Digitalizar selección"**
5. ¡Obtén el código **LaTeX** y el preview renderizado!

## 🏗️ Arquitectura

```
                    ┌─────────────────┐
                    │   Navegador     │
                    │  localhost:5555 │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Load Balancer  │
                    │   (balancer.py) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐     ...    ┌───────▼────────┐
     │   Worker 1     │            │   Worker N     │
     │ PP-FormulaNet  │            │ PP-FormulaNet  │
     │  :5556         │            │  :555X         │
     └────────────────┘            └────────────────┘
```

## 📁 Estructura del proyecto

```
ocr_matematico/
├── app.py              # Servidor Flask principal
├── balancer.py         # Load balancer
├── worker.py           # Worker con PP-FormulaNet
├── start_cluster.sh    # Script inicio cluster
├── stop_cluster.sh     # Script parada cluster
├── templates/
│   └── index.html      # Página principal
└── static/
    ├── css/style.css   # Estilos (temas claro/oscuro)
    └── js/app.js       # Lógica del canvas y API
```

## 🔧 Configuración

### Variables de entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `NUM_WORKERS` | Número de workers en cluster | `2` |
| `FORMULA_MODEL_NAME` | Modelo de fórmulas | `PP-FormulaNet_plus-L` |
| `PADDLE_DEVICE` | Dispositivo (cpu/gpu) | `cpu` |
| `PADDLE_PDX_MODEL_SOURCE` | Fuente de modelos | `huggingface` |

## 🧠 Modelos disponibles

| Modelo | Tamaño | Tokens máx | Uso recomendado |
|--------|--------|------------|-----------------|
| `PP-FormulaNet-S` | ~100MB | 1024 | Fórmulas simples |
| `PP-FormulaNet-L` | ~300MB | 1024 | Fórmulas moderadas |
| `PP-FormulaNet_plus-L` | ~700MB | **2560** | **Fórmulas complejas/anidadas** |

## 📄 API

### `POST /predict`

```json
// Request
{ "image": "data:image/png;base64,..." }

// Response
{
  "ok": true,
  "latex": "\\frac{3x+2}{\\sqrt{5x}}",
  "plain_math": "(3x+2)/sqrt(5x)",
  "worker_id": "worker-1"
}
```

### `GET /health`

```json
{
  "status": "healthy",
  "healthy_workers": 2,
  "total_workers": 2
}
```

### `GET /cluster/status`

Estadísticas detalladas del cluster y workers.

## 🐛 Solución de problemas

### Puerto en uso

```bash
./stop_cluster.sh  # Detiene todos los procesos
```

### Fórmulas no reconocidas

- Usa **trazos gruesos** (slider de grosor)
- La fórmula debe estar **completa** en la selección
- Prueba con fórmulas más simples primero

### Modelos no se descargan

Verifica conexión a internet. Los modelos se descargan de Hugging Face.

## 📝 Licencia

MIT License

## 🙏 Créditos

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - Motor OCR
- [PaddleX](https://github.com/PaddlePaddle/PaddleX) - Pipeline de fórmulas
- [MathJax](https://www.mathjax.org/) - Renderizado LaTeX
