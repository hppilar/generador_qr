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

# barcode (python-barcode)
BARCODE_AVAILABLE = True
try:
    import barcode
    from barcode.writer import ImageWriter
except Exception:
    BARCODE_AVAILABLE = False

st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")
st.title("🏷️ Generador de etiquetas QR + código de barras (estable)")

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

st.sidebar.header("Configuración de la etiqueta (mm)")
ancho_mm = st.sidebar.number_input("Ancho (mm)", min_value=30, max_value=150, value=60, step=1)
alto_mm = st.sidebar.number_input("Alto (mm)", min_value=30, max_value=150, value=80, step=1)
margen_mm = st.sidebar.number_input("Margen página (mm)", min_value=5, max_value=25, value=10, step=1)

st.sidebar.header("Tamaños de fuente (pt)")
font_sku_pt = st.sidebar.number_input("SKU (negrita)", min_value=6, max_value=36, value=12)
font_nombre_pt = st.sidebar.number_input("Nombre", min_value=6, max_value=36, value=10)

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

# generar imagen de barcode usando python-barcode (si disponible)
def generate_barcode_image(code_str, target_width_px):
    if not BARCODE_AVAILABLE:
        return None
    if not code_str or not any(ch.isdigit() for ch in code_str):
        return None
    # Usamos EAN13 si es numérico; si no, probamos Code128
    try:
        numeric = "".join(ch for ch in code_str if ch.isdigit())
        # preferir EAN13 si tiene entre 8-13 dígitos (rellenar a 12 para librería)
        if len(numeric) >= 8:
            data = numeric[-12:] if len(numeric) >= 12 else numeric.zfill(12)
            ean = barcode.get("ean13", data, writer=ImageWriter())
            bp = BytesIO()
            ean.write(bp, {"module_height": 10.0, "font_size": 7, "text_distance": 3.0})
            bp.seek(0)
            img = Image.open(bp).convert("RGB")
        else:
            # fallback a code128 (acepta cualquier)
            code128 = barcode.get("code128", code_str, writer=ImageWriter())
            bp = BytesIO()
            code128.write(bp, {"module_height": 10.0, "font_size": 7, "text_distance": 3.0})
            bp.seek(0)
            img = Image.open(bp).convert("RGB")
        # redimensionar manteniendo razón hasta target_width_px
        ratio = img.height / img.width if img.width else 1
        new_w = int(target_width_px)
        new_h = max(10, int(new_w * ratio))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        return img
    except Exception as e:
        st.warning(f"No se pudo generar barcode: {e}")
        return None

# genera la etiqueta como PIL.Image (usada para preview y para exportar)
def build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path):
    # convert mm -> px
    w_px = int(ancho_mm * MM_TO_PX)
    h_px = int(alto_mm * MM_TO_PX)
    img = Image.new("RGB", (w_px, h_px), (255,255,255))
    draw = ImageDraw.Draw(img)

    # cargar logo si existe
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            max_logo_w = int(w_px * 0.6)
            ratio = logo.width / logo.height if logo.height else 1
            logo_h = int(max_logo_w / ratio)
            logo_resized = logo.resize((max_logo_w, logo_h), Image.LANCZOS)
            logo_x = (w_px - max_logo_w)//2
            img.paste(logo_resized, (logo_x, 6), logo_resized)
            top_after_logo = 6 + logo_h + 6
        except Exception:
            top_after_logo = 10
    else:
        top_after_logo = 10

    # QR (centrado)
    qr_max_w = int(w_px * 0.6)
    qr_max_h = int(h_px * 0.35)
    qr_size = min(qr_max_w, qr_max_h)
    try:
        qr_img = qrcode.make(url)
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
        qr_x = (w_px - qr_size)//2
        qr_y = top_after_logo
        img.paste(qr_img, (qr_x, qr_y))
        after_qr = qr_y + qr_size + 6
    except Exception:
        after_qr = top_after_logo + qr_size + 6

    # fuentes: convertir pt -> px aproximado (1 pt ≈ 1.33 px at 96dpi; usamos MM_TO_PX scale)
    # mejor: tomar tamaño proporcional: px = pt * scale_factor
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

    # Código de barras (si hay)
    barcode_img = None
    if codigo_barras and BARCODE_AVAILABLE:
        try:
            target_w = int(w_px * 0.85)
            barcode_img = generate_barcode_image(codigo_barras, target_w)
            if barcode_img:
                # pegar en bottom con un pequeño margen
                b_w, b_h = barcode_img.size
                bx = (w_px - b_w)//2
                by = h_px - b_h - 6
                img.paste(barcode_img, (bx, by))
        except Exception as e:
            st.warning(f"Error generando barcode en preview: {e}")

    return img

# --- Flujo principal ---
if archivo is None:
    st.info("Cargá tu archivo Excel para comenzar.")
else:
    try:
        df = pd.read_excel(archivo)
    except Exception as e:
        st.error(f"Error leyendo Excel: {e}")
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
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            page_w, page_h = A4
            # generar cada etiqueta y pintarla en el PDF
            for i, row in df.iterrows():
                sku = str(row.get("sku",""))
                nombre = str(row.get("nombre",""))
                url = str(row.get("url",""))
                codigo_barras = str(row.get("codigo_barras","")) if "codigo_barras" in df.columns else ""

                img_label = build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH)
                buf_img = BytesIO()
                img_label.save(buf_img, format="PNG")
                buf_img.seek(0)
                img_reader = ImageReader(buf_img)

                idx = i
                col = idx % cols
                rown = (idx // cols) % rows
                x = margen_mm*mm + col * ancho_mm * mm
                y = page_h - ((margen_mm + (rown+1)*alto_mm) * mm)

                c.drawImage(img_reader, x, y, ancho_mm*mm, alto_mm*mm)
                # nueva página si completa
                if (i+1) % (cols*rows) == 0:
                    c.showPage()
            c.save()
            buffer.seek(0)
            st.success("PDF generado ✅")
            st.download_button("Descargar etiquetas (PDF)", buffer, file_name="etiquetas_qr.pdf", mime="application/pdf")

# Informar sobre dependencias
if not BARCODE_AVAILABLE:
    st.info("La librería 'python-barcode' no está instalada: los códigos de barra no se generarán. "
            "Añadila a requirements.txt si querés esa función.")





