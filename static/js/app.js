/**
 * OCR Matemático - Canvas Drawing & Selection
 */

class MathCanvasApp {
    constructor() {
        // Canvas elements
        this.canvas = document.getElementById('drawing-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.canvasWrapper = document.querySelector('.canvas-wrapper');
        this.selectionBox = document.getElementById('selection-box');

        // Tool buttons
        this.btnDraw = document.getElementById('btn-draw');
        this.btnSelect = document.getElementById('btn-select');
        this.btnErase = document.getElementById('btn-erase');
        this.btnClear = document.getElementById('btn-clear');
        this.btnDigitize = document.getElementById('btn-digitize');
        this.btnCopy = document.getElementById('btn-copy');
        this.themeToggle = document.getElementById('theme-toggle');

        // Tool controls
        this.strokeWidthInput = document.getElementById('stroke-width');
        this.strokeWidthValue = document.getElementById('stroke-value');
        this.strokeColorInput = document.getElementById('stroke-color');

        // Result elements
        this.loading = document.getElementById('loading');
        this.resultContent = document.getElementById('result-content');
        this.latexOutput = document.getElementById('latex-output');
        this.latexCode = document.getElementById('latex-code');
        this.renderedOutput = document.getElementById('rendered-output');
        this.mathPreview = document.getElementById('math-preview');

        // State
        this.mode = 'draw'; // 'draw', 'select', 'erase'
        this.isDrawing = false;
        this.isSelecting = false;
        this.lastX = 0;
        this.lastY = 0;
        this.strokeWidth = 3;
        this.isDarkTheme = true;
        this.strokeColor = '#ffffff'; // Default for dark theme

        // Selection
        this.selection = null;
        this.selectionStart = null;

        // Initialize
        this.init();
    }

    init() {
        this.setupCanvas();
        this.bindEvents();
        this.setMode('draw');
        this.initTheme();
    }

    setupCanvas() {
        // Set canvas size to match container
        const rect = this.canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = rect.height + 'px';

        this.ctx.scale(dpr, dpr);
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        // Store dimensions for coordinate conversion
        this.canvasWidth = rect.width;
        this.canvasHeight = rect.height;
    }

    bindEvents() {
        // Tool buttons
        this.btnDraw.addEventListener('click', () => this.setMode('draw'));
        this.btnSelect.addEventListener('click', () => this.setMode('select'));
        this.btnErase.addEventListener('click', () => this.setMode('erase'));
        this.btnClear.addEventListener('click', () => this.clearCanvas());
        this.btnDigitize.addEventListener('click', () => this.digitizeSelection());
        this.btnCopy.addEventListener('click', () => this.copyLatex());
        this.themeToggle.addEventListener('click', () => this.toggleTheme());

        // Tool controls
        this.strokeWidthInput.addEventListener('input', (e) => {
            this.strokeWidth = parseInt(e.target.value);
            this.strokeWidthValue.textContent = this.strokeWidth;
        });

        this.strokeColorInput.addEventListener('input', (e) => {
            this.strokeColor = e.target.value;
        });

        // Canvas events - Mouse
        this.canvas.addEventListener('mousedown', (e) => this.handleStart(e));
        this.canvas.addEventListener('mousemove', (e) => this.handleMove(e));
        this.canvas.addEventListener('mouseup', (e) => this.handleEnd(e));
        this.canvas.addEventListener('mouseleave', (e) => this.handleEnd(e));

        // Canvas events - Touch
        this.canvas.addEventListener('touchstart', (e) => this.handleStart(e));
        this.canvas.addEventListener('touchmove', (e) => this.handleMove(e));
        this.canvas.addEventListener('touchend', (e) => this.handleEnd(e));

        // Window resize
        window.addEventListener('resize', () => {
            // Debounce resize
            clearTimeout(this.resizeTimeout);
            this.resizeTimeout = setTimeout(() => this.handleResize(), 250);
        });
    }

    setMode(mode) {
        this.mode = mode;

        // Update button states
        [this.btnDraw, this.btnSelect, this.btnErase].forEach(btn => {
            btn.classList.remove('active');
        });

        if (mode === 'draw') {
            this.btnDraw.classList.add('active');
            this.canvas.style.cursor = 'crosshair';
        } else if (mode === 'select') {
            this.btnSelect.classList.add('active');
            this.canvas.style.cursor = 'crosshair';
        } else if (mode === 'erase') {
            this.btnErase.classList.add('active');
            this.canvas.style.cursor = 'cell';
        }

        // Clear selection when switching modes
        if (mode !== 'select') {
            this.clearSelection();
        }
    }

    getCoordinates(e) {
        const rect = this.canvas.getBoundingClientRect();
        let x, y;

        if (e.touches && e.touches.length > 0) {
            x = e.touches[0].clientX - rect.left;
            y = e.touches[0].clientY - rect.top;
        } else {
            x = e.clientX - rect.left;
            y = e.clientY - rect.top;
        }

        return { x, y };
    }

    handleStart(e) {
        e.preventDefault();
        const { x, y } = this.getCoordinates(e);

        if (this.mode === 'select') {
            this.isSelecting = true;
            this.selectionStart = { x, y };
            this.selection = null;
            this.selectionBox.classList.remove('hidden');
            this.updateSelectionBox(x, y, 0, 0);
        } else {
            this.isDrawing = true;
            this.lastX = x;
            this.lastY = y;

            // Start a new path
            this.ctx.beginPath();
            this.ctx.moveTo(x, y);
        }
    }

    handleMove(e) {
        e.preventDefault();
        const { x, y } = this.getCoordinates(e);

        if (this.mode === 'select' && this.isSelecting) {
            const width = x - this.selectionStart.x;
            const height = y - this.selectionStart.y;

            // Calculate selection rectangle (handle negative dimensions)
            const left = width >= 0 ? this.selectionStart.x : x;
            const top = height >= 0 ? this.selectionStart.y : y;
            const w = Math.abs(width);
            const h = Math.abs(height);

            this.selection = { x: left, y: top, width: w, height: h };
            this.updateSelectionBox(left, top, w, h);
        } else if (this.isDrawing) {
            if (this.mode === 'draw') {
                this.ctx.strokeStyle = this.strokeColor;
                this.ctx.lineWidth = this.strokeWidth;
            } else if (this.mode === 'erase') {
                this.ctx.strokeStyle = '#1e1e2e'; // Canvas background color
                this.ctx.lineWidth = this.strokeWidth * 3;
            }

            this.ctx.lineTo(x, y);
            this.ctx.stroke();
            this.ctx.beginPath();
            this.ctx.moveTo(x, y);

            this.lastX = x;
            this.lastY = y;
        }
    }

    handleEnd(e) {
        if (this.isSelecting) {
            this.isSelecting = false;

            // Enable digitize button if selection is valid
            if (this.selection && this.selection.width > 10 && this.selection.height > 10) {
                this.btnDigitize.disabled = false;
            }
        }

        if (this.isDrawing) {
            this.isDrawing = false;
            this.ctx.beginPath();
        }
    }

    handleResize() {
        // Save canvas content
        const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);

        // Resize canvas
        this.setupCanvas();

        // Restore content (may need scaling for proper resize)
        this.ctx.putImageData(imageData, 0, 0);
    }

    updateSelectionBox(x, y, width, height) {
        this.selectionBox.style.left = x + 'px';
        this.selectionBox.style.top = y + 'px';
        this.selectionBox.style.width = width + 'px';
        this.selectionBox.style.height = height + 'px';
    }

    clearSelection() {
        this.selection = null;
        this.selectionBox.classList.add('hidden');
        this.btnDigitize.disabled = true;
    }

    clearCanvas() {
        const dpr = window.devicePixelRatio || 1;
        this.ctx.clearRect(0, 0, this.canvas.width / dpr, this.canvas.height / dpr);
        this.clearSelection();

        // Reset results
        this.resultContent.innerHTML = `
            <div class="result-empty">
                <p>Dibuja una fórmula, selecciona el área y haz clic en "Digitalizar"</p>
            </div>
        `;
        this.latexOutput.classList.add('hidden');
        this.renderedOutput.classList.add('hidden');
    }

    async digitizeSelection() {
        if (!this.selection) return;

        // Extract selected area from canvas
        const dpr = window.devicePixelRatio || 1;
        const { x, y, width, height } = this.selection;

        // Create a temporary canvas for the selection
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = width * dpr;
        tempCanvas.height = height * dpr;
        const tempCtx = tempCanvas.getContext('2d');

        // Fill with white background
        tempCtx.fillStyle = '#ffffff';
        tempCtx.fillRect(0, 0, tempCanvas.width, tempCanvas.height);

        // Get image data from the original canvas selection
        const imageData = this.ctx.getImageData(x * dpr, y * dpr, width * dpr, height * dpr);
        const data = imageData.data;

        // Process pixels: convert to black on white
        // In dark mode: white/light strokes on transparent background
        // In light mode: black/dark strokes on transparent background
        // Target: black strokes on white background
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const a = data[i + 3];

            // If pixel has significant alpha (is drawn), it's part of the drawing
            const isDrawing = a > 50;

            if (isDrawing) {
                // This is our drawing - make it black
                data[i] = 0;     // R
                data[i + 1] = 0; // G
                data[i + 2] = 0; // B
                data[i + 3] = 255; // A - fully opaque
            } else {
                // This is background - make it white
                data[i] = 255;     // R
                data[i + 1] = 255; // G
                data[i + 2] = 255; // B
                data[i + 3] = 255; // A - fully opaque
            }
        }

        // Put the processed image
        tempCtx.putImageData(imageData, 0, 0);

        // Convert to base64
        const imageBase64 = tempCanvas.toDataURL('image/png');

        // Show loading
        this.showLoading(true);

        try {
            const response = await fetch('/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    image: imageBase64
                })
            });

            const result = await response.json();

            if (result.ok) {
                this.displayResult(result.latex, result.demo_mode);
            } else {
                this.showError(result.error || 'Error desconocido');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showError('Error de conexión con el servidor');
        } finally {
            this.showLoading(false);
        }
    }

    showLoading(show) {
        if (show) {
            this.loading.classList.remove('hidden');
            this.resultContent.querySelector('.result-empty')?.remove();
        } else {
            this.loading.classList.add('hidden');
        }
    }

    displayResult(latex, isDemoMode = false) {
        // Show LaTeX code
        this.latexCode.textContent = latex;
        this.latexOutput.classList.remove('hidden');

        // Render with MathJax
        this.mathPreview.innerHTML = isDemoMode
            ? `<span style="font-size: 0.7rem; color: #888;">(Demo)</span> \\[${latex}\\]`
            : `\\[${latex}\\]`;
        this.renderedOutput.classList.remove('hidden');

        // Trigger MathJax to render
        if (window.MathJax) {
            MathJax.typesetPromise([this.mathPreview]).catch((err) => {
                console.error('MathJax error:', err);
            });
        }

        // Update result content
        this.resultContent.innerHTML = `
            <div style="text-align: center; color: #22c55e;">
                ✅ Fórmula reconocida${isDemoMode ? ' (modo demo)' : ''}
            </div>
        `;
    }

    showError(message) {
        this.resultContent.innerHTML = `
            <div style="text-align: center; color: #ef4444;">
                ❌ ${message}
            </div>
        `;
    }

    copyLatex() {
        const latex = this.latexCode.textContent;
        navigator.clipboard.writeText(latex).then(() => {
            this.showToast('¡LaTeX copiado al portapapeles!');
        }).catch(err => {
            console.error('Error al copiar:', err);
        });
    }

    showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    initTheme() {
        // Check for saved theme preference or default to dark
        const savedTheme = localStorage.getItem('ocr-theme');
        if (savedTheme === 'light') {
            this.isDarkTheme = false;
            document.documentElement.setAttribute('data-theme', 'light');
            this.updateThemeUI();
        }
    }

    toggleTheme() {
        this.isDarkTheme = !this.isDarkTheme;

        if (this.isDarkTheme) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('ocr-theme', 'dark');
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem('ocr-theme', 'light');
        }

        this.updateThemeUI();
        this.clearCanvas(); // Clear canvas on theme change to avoid color conflicts
    }

    updateThemeUI() {
        const icon = this.themeToggle.querySelector('.icon');

        if (this.isDarkTheme) {
            icon.textContent = '🌙';
            this.strokeColor = '#ffffff';
            this.strokeColorInput.value = '#ffffff';
        } else {
            icon.textContent = '☀️';
            this.strokeColor = '#000000';
            this.strokeColorInput.value = '#000000';
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new MathCanvasApp();
});
