import streamlit as st
import pandas as pd
from io import BytesIO
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
import tempfile
import os

# --- CONFIGURACIÓN DE LA APP ---
st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")
st.title("📦 Generador de etiquetas con QR, Logo y Código de Barras")

st.markdown("""
Subí un archivo Excel con las siguientes columnas:
- **sku**
- **nombre**
- **url** (dirección web a enlazar)
- **codigo_barras** (número secuencial o código EAN13 válido)
""")

# --- ARCHIVO DE LOGO ---
logo_file = st.file_uploader("📷 Subí el logo (formato PNG o JPG)", type=["png", "jpg", "jpeg"])

# --- ARCHIVO DE EXCEL ---
archivo = st.file_uploader("📄 Subí tu archivo Excel", type=["xlsx"])

# --- CONFIGURACIÓN DE TAMAÑOS ---
st.sidebar.header("⚙️ Configuración de etiqueta (en mm)")
ancho_etiqueta = st.sidebar.number_input("Ancho de etiqueta", min_value=40.0, max_value=150.0, value=60.0, step=5.0)
alto_etiqueta = st.sidebar.number_input("Alto de etiqueta", min_value=40.0, max_value=150.0, value=80.0, step=5.0)

font_nombre_size = st.sidebar.number_input("Tamaño de fuente para nombre", min_value=6, max_value=24, value=10)
font_sku_size = st.sidebar.number_input("Tamaño de fuente para SKU (negrita)", min_value=6, max_value=24, value=12)

# --- FUNCIÓN AUXILIAR PARA TEXTO CENTRADO Y AJUSTADO ---
def draw_centered_wrapped_text(draw, text, x_center, y_top, font, max_width):
    lines = []
    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        bbox = font.getbbox(test_line)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            line = test_line
        else:
            lines.append(line)
            line = word
    lines.append(line)

    h = 0
    for line in lines:
        bbox = font.getbbox(line)
        h += (bbox[3] - bbox[1]) + 2

    y = y_top
    for line in lines:
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        draw.text((x_center - w / 2, y), line, font=font, fill="black")
        y += (bbox[3] - bbox[1]) + 2

    return h

# --- GENERACIÓN DE PDF ---
if archivo and logo_file:
    df = pd.read_excel(archivo)
    st.success(f"{len(df)} artículos cargados correctamente ✅")

    buffer_pdf = BytesIO()
    c = canvas.Canvas(buffer_pdf, pagesize=A4)
    page_width, page_height = A4

    cols = int(page_width // (ancho_etiqueta * mm))
    rows = int(page_height // (alto_etiqueta * mm))

    x0, y0 = 10 * mm, page_height - alto_etiqueta * mm - 10 * mm

    logo = Image.open(logo_file).convert("RGBA")

    for i, row in df.iterrows():
        sku = str(row.get("sku", ""))
        nombre = str(row.get("nombre", ""))
        url = str(row.get("url", ""))
        codigo_barras = str(row.get("codigo_barras", ""))

        col = i % cols
        fila = (i // cols) % rows
        x = x0 + col * (ancho_etiqueta * mm)
        y = y0 - fila * (alto_etiqueta * mm)

        # --- LOGO ---
        max_logo_width = ancho_etiqueta * mm * 0.7
        aspect_ratio = logo.height / logo.width
        logo_height = max_logo_width * aspect_ratio
        logo_resized = logo.resize((int(max_logo_width), int(logo_height)))
        logo_buf = BytesIO()
        logo_resized.save(logo_buf, format="PNG")
        logo_buf.seek(0)
        logo_img = ImageReader(logo_buf)
        c.drawImage(
            logo_img,
            x + (ancho_etiqueta * mm - max_logo_width) / 2,
            y + alto_etiqueta * mm - logo_height - 5,
            width=max_logo_width,
            height=logo_height,
            mask="auto",
        )

        # --- CÓDIGO QR ---
        qr = qrcode.make(url)
        qr_buf = BytesIO()
        qr.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        qr_img = ImageReader(qr_buf)

        qr_size = min(ancho_etiqueta, alto_etiqueta) * 0.35 * mm
        c.drawImage(
            qr_img,
            x + (ancho_etiqueta * mm - qr_size) / 2,
            y + alto_etiqueta * mm / 2 - qr_size / 2,
            width=qr_size,
            height=qr_size,
        )

        # --- TEXTO SKU (EN NEGRITA) Y NOMBRE ---
        # Crear imagen temporal con texto renderizado
        label_img = Image.new("RGB", (int(ancho_etiqueta * 4), int(alto_etiqueta * 4)), "white")
        draw = ImageDraw.Draw(label_img)

        try:
            font_sku = ImageFont.truetype("arialbd.ttf", font_sku_size * 4)
            font_nombre = ImageFont.truetype("arial.ttf", font_nombre_size * 4)
        except:
            font_sku = ImageFont.load_default()
            font_nombre = ImageFont.load_default()

        current_y = int(alto_etiqueta * 2.8)  # posición relativa

        # --- SKU (primero, en negrita) ---
        h_sku = draw_centered_wrapped_text(draw, sku, label_img.width // 2, current_y, font_sku, label_img.width - 10)

        # --- Nombre (debajo) ---
        current_y += h_sku + 10
        draw_centered_wrapped_text(draw, nombre, label_img.width // 2, current_y, font_nombre, label_img.width - 10)

        text_buf = BytesIO()
        label_img.save(text_buf, format="PNG")
        text_buf.seek(0)
        text_img = ImageReader(text_buf)

        c.drawImage(
            text_img,
            x,
            y,
            width=ancho_etiqueta * mm,
            height=alto_etiqueta * mm,
            mask="auto",
        )

        # --- CÓDIGO DE BARRAS ---
        if codigo_barras and codigo_barras.isdigit():
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            ean = barcode.get("ean13", codigo_barras, writer=ImageWriter())
            ean.save(tmp.name[:-4])
            c.drawImage(
                tmp.name,
                x + (ancho_etiqueta * mm - 40 * mm) / 2,
                y + 5,
                width=40 * mm,
                height=15 * mm,
                mask="auto",
            )
            os.unlink(tmp.name)

        if (i + 1) % (cols * rows) == 0:
            c.showPage()
            x0, y0 = 10 * mm, page_height - alto_etiqueta * mm - 10 * mm

    c.save()
    buffer_pdf.seek(0)

    st.download_button("⬇️ Descargar etiquetas en PDF", buffer_pdf, file_name="etiquetas_qr.pdf", mime="application/pdf")

else:
    st.info("Subí el logo y el archivo Excel para generar las etiquetas.")
