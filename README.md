# 🧮 OCR Matemático

Aplicación web para reconocimiento de fórmulas matemáticas escritas a mano. Dibuja una fórmula en el canvas, selecciona el área y obtén el código LaTeX correspondiente.

![Demo](https://img.shields.io/badge/Status-Working-green) ![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20Silicon-silver)

## ✨ Características

- 🖌️ **Canvas de dibujo** con soporte para mouse y touch
- 🔲 **Selección de área** para reconocimiento específico
- 🧠 **PaddleOCR VL** - Modelo Vision-Language especializado en fórmulas
- 📐 **Salida LaTeX** con preview renderizado (MathJax)
- 🎨 **Interfaz moderna** con tema oscuro y efectos glassmorphism

## 📋 Requisitos

- macOS con Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- ~4GB de espacio libre (modelos PaddleOCR)

## 🚀 Instalación en Mac Silicon

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
# Actualizar pip
pip install --upgrade pip

# Instalar PaddlePaddle (CPU para Mac Silicon)
pip install paddlepaddle

# Instalar PaddleOCR con soporte para documentos
pip install "paddleocr[doc-parser]"

# Instalar dependencias web
pip install Flask Pillow gunicorn requests
```

> **Nota:** La primera vez que ejecutes la aplicación, PaddleOCR descargará los modelos (~2GB). Esto puede tardar unos minutos.

### 4. Verificar instalación

```bash
python -c "from paddleocr import PaddleOCRVL; print('✅ PaddleOCRVL instalado correctamente')"
```

## ▶️ Ejecución

### Modo desarrollo

```bash
# Puerto por defecto (8000)
python app.py

# Puerto personalizado
PORT=5555 python app.py
```

Abre en el navegador: **http://localhost:5555**

### Modo producción (Gunicorn)

```bash
gunicorn -w 1 -b 0.0.0.0:8000 app:app
```

> ⚠️ **Importante:** Usa solo 1 worker (`-w 1`) porque PaddleOCR no es thread-safe.

## 🎯 Uso

1. **Dibuja** una fórmula matemática en el canvas negro
2. Haz clic en **"Seleccionar"** (ícono de cuadrado)
3. **Arrastra** para seleccionar el área de la fórmula
4. Haz clic en **"Digitalizar selección"**
5. ¡Obtén el código **LaTeX** y el preview renderizado!

## 📁 Estructura del proyecto

```
ocr_matematico/
├── app.py              # Servidor Flask + PaddleOCR VL
├── requirements.txt    # Dependencias Python
├── templates/
│   └── index.html      # Página principal
└── static/
    ├── css/
    │   └── style.css   # Estilos (tema oscuro)
    └── js/
        └── app.js      # Lógica del canvas y API
```

## 🔧 Configuración

### Variables de entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `PORT` | Puerto del servidor | `8000` |
| `USE_LAYOUT_DETECTION` | Detectar layout de documento | `true` |
| `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` | Saltar verificación de modelos | `True` |

## 🐛 Solución de problemas

### Error: "Address already in use"

```bash
# Encontrar el proceso usando el puerto
lsof -i :5555

# Matar el proceso
kill -9 <PID>
```

### Modelos no se descargan

Verifica tu conexión a internet. Los modelos se descargan de Hugging Face (~2GB).

### Reconocimiento vacío

- Asegúrate de que el trazo sea **visible y claro**
- Dibuja con **líneas gruesas** (ajusta el grosor)
- La fórmula debe tener **buen contraste**

## 📄 API

### `POST /predict`

**Request:**
```json
{
  "image": "data:image/png;base64,..."
}
```

**Response:**
```json
{
  "ok": true,
  "latex": "3x+2",
  "demo_mode": false
}
```

### `GET /health`

```json
{
  "status": "ok",
  "paddle_available": true,
  "model": "PaddleOCRVL",
  "use_layout_detection": true
}
```

## 📝 Licencia

MIT License

## 🙏 Créditos

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - Motor OCR
- [MathJax](https://www.mathjax.org/) - Renderizado LaTeX
