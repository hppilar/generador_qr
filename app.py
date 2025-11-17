# app.py - Generador estable y robusto de etiquetas con QR y código de barras
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
import logging

# Configuración de logging para mejor depuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# barcode (python-barcode)
BARCODE_AVAILABLE = True
try:
    import barcode
    from barcode.writer import ImageWriter
except Exception as e:
    BARCODE_AVAILABLE = False
    logger.warning(f"No se pudo importar la librería barcode: {e}")

st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")
st.title("🏷️ Generador de etiquetas QR + código de barras (mejorado)")

# Ruta fija del logo (archivo en la raíz del repo)
LOGO_PATH = "logo.png"
if not os.path.exists(LOGO_PATH):
    st.warning("No se encontró logo.png en la carpeta del proyecto. Subí logo.png o colócalo en la raíz.")
else:
    st.image(LOGO_PATH, width=140)

st.markdown("""
Subí un Excel con columnas: **sku**, **nombre**, **url**, **codigo_barras** (opcional).
- SKU se dibuja *primero* (en negrita).
- Luego Nombre.
- Código de barras (si hay número válido) en la parte inferior.
""")

# --- Inputs
archivo = st.file_uploader("Cargar Excel (.xlsx)", type=["xlsx"])

# Panel lateral para configuración
with st.sidebar:
    st.header("Configuración de la etiqueta (mm)")
    ancho_mm = st.number_input("Ancho (mm)", min_value=30, max_value=150, value=60, step=1)
    alto_mm = st.number_input("Alto (mm)", min_value=30, max_value=150, value=80, step=1)
    margen_mm = st.number_input("Margen página (mm)", min_value=5, max_value=25, value=10, step=1)
    
    st.header("Tamaños de fuente (pt)")
    font_sku_pt = st.number_input("SKU (negrita)", min_value=6, max_value=36, value=12)
    font_nombre_pt = st.number_input("Nombre", min_value=6, max_value=36, value=10)
    
    st.header("Opciones adicionales")
    mostrar_codigo_qr = st.checkbox("Mostrar código QR", value=True)
    mostrar_codigo_barras = st.checkbox("Mostrar código de barras", value=True)
    mostrar_logo = st.checkbox("Mostrar logo", value=True)
    qr_error_correction = st.selectbox("Nivel de corrección de errores QR", 
                                      ["L", "M", "Q", "H"], 
                                      help="L: Bajo (7%), M: Medio (15%), Q: Alto (25%), H: Máximo (30%)")
    
    st.header("Procesamiento")
    procesamiento_paralelo = st.checkbox("Procesamiento paralelo (más rápido)", value=True)

# conversión mm -> px para preview (alto DPI para mejor detalle)
MM_TO_PX = 4  # 4 px per mm -> 4*25.4 ≈ 101.6 DPI; ajustable

# helpers para fuentes (intenta varias fuentes comunes)
def get_font(preferred_names, size_px):
    for name in preferred_names:
        try:
            return ImageFont.truetype(name, size_px)
        except Exception:
            continue
    try:
        # fallback a la fuente por defecto escalada (no ideal pero segura)
        return ImageFont.load_default()
    except Exception:
        return None

PREFERRED_BOLD = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf"]
PREFERRED_REG = ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "LiberationSans-Regular.ttf"]

# función para dibujar texto centrado con wrap usando textbbox
def draw_centered_wrapped(draw, text, x_center, y_top, font, max_width):
    if not text or text.strip() == "":
        return 0
        
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        w_px = bbox[2] - bbox[0]
        if w_px <= max_width or current == "":
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    y = y_top
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        w_px = bbox[2] - bbox[0]
        h_px = bbox[3] - bbox[1]
        draw.text((x_center - w_px/2, y), line, font=font, fill=(0,0,0))
        y += h_px + 2
        total_h += h_px + 2
    return total_h

### CAMBIO 1: Lógica de generación de código de barras ###
# generar imagen de barcode usando python-barcode (si disponible)
def generate_barcode_image(code_str, target_width_px, target_height_px):
    """
    Genera una imagen de código de barras Code128 con dimensiones fijas.
    Code128 se utiliza universalmente porque soporta códigos numéricos y alfanuméricos
    sin necesidad de padding o modificación, evitando problemas de escaneo.
    """
    if not BARCODE_AVAILABLE or not code_str:
        return None
    
    try:
        # Siempre usar Code128, ya que maneja tanto alfanuméricos como numéricos sin padding.
        # Esto resuelve el problema de los códigos que no se encuentran al escanearse.
        code128 = barcode.get('code128', code_str, writer=ImageWriter())
        bp = BytesIO()
        # Generar el código de barras con opciones por defecto
        code128.write(bp, options={'module_height': 8.0, 'font_size': 6, 'text_distance': 2.0})
        bp.seek(0)
        img = Image.open(bp).convert('RGB')

        # Redimensionar a las dimensiones exactas requeridas (ancho y alto constantes)
        img = img.resize((target_width_px, target_height_px), Image.LANCZOS)
        return img
    except Exception as e:
        logger.warning(f"No se pudo generar barcode para '{code_str}': {e}")
        return None

# genera la etiqueta como PIL.Image (usada para preview y para exportar)
def build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path):
    # convert mm -> px
    w_px = int(ancho_mm * MM_TO_PX)
    h_px = int(alto_mm * MM_TO_PX)
    img = Image.new("RGB", (w_px, h_px), (255,255,255))
    draw = ImageDraw.Draw(img)

    # cargar logo si existe y está habilitado
    top_after_logo = 10
    if mostrar_logo and logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            max_logo_w = int(w_px * 0.6)
            ratio = logo.width / logo.height if logo.height else 1
            logo_h = int(max_logo_w / ratio)
            logo_resized = logo.resize((max_logo_w, logo_h), Image.LANCZOS)
            logo_x = (w_px - max_logo_w)//2
            img.paste(logo_resized, (logo_x, 6), logo_resized)
            top_after_logo = 6 + logo_h + 6
        except Exception as e:
            logger.warning(f"Error al cargar logo: {e}")
            top_after_logo = 10

    # QR (centrado) si está habilitado
    after_qr = top_after_logo
    if mostrar_codigo_qr and url:
        qr_max_w = int(w_px * 0.6)
        qr_max_h = int(h_px * 0.35)
        qr_size = min(qr_max_w, qr_max_h)
        try:
            # Mapeo de nivel de corrección de errores
            error_correction_map = {
                "L": qrcode.constants.ERROR_CORRECT_L,
                "M": qrcode.constants.ERROR_CORRECT_M,
                "Q": qrcode.constants.ERROR_CORRECT_Q,
                "H": qrcode.constants.ERROR_CORRECT_H
            }
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=error_correction_map.get(qr_error_correction, qrcode.constants.ERROR_CORRECT_M),
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
            qr_x = (w_px - qr_size)//2
            qr_y = top_after_logo
            img.paste(qr_img, (qr_x, qr_y))
            after_qr = qr_y + qr_size + 6
        except Exception as e:
            logger.warning(f"Error generando QR: {e}")
            after_qr = top_after_logo + qr_size + 6

    # fuentes: convertir pt -> px aproximado
    scale = MM_TO_PX / 3.0  # heurística para convertir pt -> px
    sku_px = max(8, int(font_sku_pt * scale))
    nombre_px = max(7, int(font_nombre_pt * scale))
    font_sku = get_font(PREFERRED_BOLD, sku_px)
    font_nombre = get_font(PREFERRED_REG, nombre_px)

    # SKU (primero, bold)
    h_sku = draw_centered_wrapped(draw, sku, w_px//2, after_qr, font_sku, int(w_px*0.9))
    y_after_sku = after_qr + h_sku + 4

    # Nombre (debajo)
    h_name = draw_centered_wrapped(draw, nombre, w_px//2, y_after_sku, font_nombre, int(w_px*0.9))
    y_after_name = y_after_sku + h_name + 4

    # Código de barras (si hay y está habilitado)
    if mostrar_codigo_barras and codigo_barras and BARCODE_AVAILABLE:
        try:
            target_w = int(w_px * 0.85)
            ### CAMBIO 2: Altura constante y llamada a la función modificada ###
            target_h_px = int(15 * MM_TO_PX) # Altura fija de 15mm convertida a píxeles
            barcode_img = generate_barcode_image(codigo_barras, target_w, target_h_px)
            
            if barcode_img:
                # pegar en bottom con un pequeño margen
                b_w, b_h = barcode_img.size
                bx = (w_px - b_w)//2
                by = h_px - b_h - 6
                img.paste(barcode_img, (bx, by))
        except Exception as e:
            logger.warning(f"Error generando barcode en preview: {e}")

    return img

# Función para generar etiquetas en paralelo
def generar_etiquetas_paralelo(df, cols, rows, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_w, page_h = A4
    
    # Función para procesar una etiqueta individual
    def procesar_etiqueta(i, row):
        sku = str(row.get("sku",""))
        nombre = str(row.get("nombre",""))
        url = str(row.get("url",""))
        codigo_barras = str(row.get("codigo_barras","")) if "codigo_barras" in df.columns else ""
        
        img_label = build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path)
        buf_img = BytesIO()
        img_label.save(buf_img, format="PNG")
        buf_img.seek(0)
        img_reader = ImageReader(buf_img)
        
        idx = i
        col = idx % cols
        rown = (idx // cols) % rows
        x = margen_mm*mm + col * ancho_mm * mm
        y = page_h - ((margen_mm + (rown+1)*alto_mm) * mm)
        
        return (img_reader, x, y)
    
    # Procesar etiquetas en paralelo si está habilitado
    if procesamiento_paralelo:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i, row in df.iterrows():
                futures.append(executor.submit(procesar_etiqueta, i, row))
            
            for i, future in enumerate(futures):
                img_reader, x, y = future.result()
                c.drawImage(img_reader, x, y, ancho_mm*mm, alto_mm*mm)
                
                # nueva página si completa
                if (i+1) % (cols*rows) == 0:
                    c.showPage()
    else:
        # Procesamiento secuencial
        for i, row in df.iterrows():
            img_reader, x, y = procesar_etiqueta(i, row)
            c.drawImage(img_reader, x, y, ancho_mm*mm, alto_mm*mm)
            
            # nueva página si completa
            if (i+1) % (cols*rows) == 0:
                c.showPage()
    
    c.save()
    buffer.seek(0)
    return buffer

# --- Flujo principal ---
if archivo is None:
    st.info("Cargá tu archivo Excel para comenzar.")
else:
    try:
        df = pd.read_excel(archivo)
    except Exception as e:
        st.error(f"Error leyendo Excel: {e}")
        logger.error(f"Error leyendo Excel: {e}")
        st.stop()

    # normalizar nombres de columna a minúsculas para tolerancia
    df.columns = [c.strip() for c in df.columns]
    lower_map = {c: c.lower() for c in df.columns}
    df.rename(columns=lower_map, inplace=True)

    # comprobar columnas mínimas
    if not all(col in df.columns for col in ["sku","nombre","url"]):
        st.error("El Excel debe contener al menos las columnas: sku, nombre, url")
        st.stop()

    st.success(f"{len(df)} filas leídas")

    # Validación de datos
    st.subheader("Validación de datos")
    with st.expander("Verificar datos"):
        st.dataframe(df.head(10))
        
        # Verificar URLs vacías
        urls_vacias = df['url'].isna().sum()
        if urls_vacias > 0:
            st.warning(f"Se encontraron {urls_vacias} URLs vacías. Estas etiquetas no tendrán código QR.")
        
        # Verificar códigos de barras vacíos
        if 'codigo_barras' in df.columns:
            barras_vacios = df['codigo_barras'].isna().sum()
            if barras_vacios > 0:
                st.warning(f"Se encontraron {barras_vacios} códigos de barras vacíos.")


    # Previsualización de la primera fila
    st.subheader("Previsualización (fila 1)")
    first = df.iloc[0]
    sku = str(first.get("sku",""))
    nombre = str(first.get("nombre",""))
    url = str(first.get("url",""))
    codigo_barras = str(first.get("codigo_barras","")) if "codigo_barras" in df.columns else ""

    img_preview = build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH)
    st.image(img_preview, width=min(400, img_preview.width))

    # Generar PDF
    if st.button("Generar PDF (A4)"):
        # Validaciones: asegurar que al menos 1 etiqueta cabe en A4
        cols = int((210 - 2*margen_mm)//ancho_mm)
        rows = int((297 - 2*margen_mm)//alto_mm)
        if cols < 1 or rows < 1:
            st.error("Con ese tamaño y margen no cabe ninguna etiqueta en A4. Ajustá medidas.")
        else:
            # Barra de progreso
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            start_time = time.time()
            
            try:
                buffer = generar_etiquetas_paralelo(df, cols, rows, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH)
                
                elapsed_time = time.time() - start_time
                status_text.text(f"PDF generado en {elapsed_time:.2f} segundos")
                progress_bar.progress(100)
                
                st.success("PDF generado ✅")
                st.download_button("Descargar etiquetas (PDF)", buffer, file_name="etiquetas_qr.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error al generar PDF: {e}")
                logger.error(f"Error al generar PDF: {e}")

# Informar sobre dependencias
if not BARCODE_AVAILABLE:
    st.info("La librería 'python-barcode' no está instalada: los códigos de barra no se generarán. "
            "Añadila a requirements.txt si querés esa función.")
