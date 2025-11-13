import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import math
import os

# --- CONFIGURACIÓN GENERAL ---
st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")
st.title("🏷️ Generador de etiquetas QR con logo")

LOGO_PATH = "logo.png"  # logo fijo en la carpeta

if not os.path.exists(LOGO_PATH):
    st.error("⚠️ No se encontró el archivo logo.png en la carpeta del proyecto.")
else:
    st.image(LOGO_PATH, width=120)

st.markdown("""
Subí tu archivo Excel con las columnas:
- **sku**
- **nombre**
- **url**
""")

archivo = st.file_uploader("📄 Cargar archivo Excel", type=["xlsx"])

# --- PARÁMETROS DE ETIQUETA ---
st.sidebar.header("⚙️ Configuración de etiqueta")
ancho_mm = st.sidebar.number_input("Ancho (mm)", 40, 150, 60, 5)
alto_mm = st.sidebar.number_input("Alto (mm)", 40, 150, 80, 5)

font_sku_size = st.sidebar.number_input("Tamaño fuente SKU (negrita)", 6, 24, 12)
font_nombre_size = st.sidebar.number_input("Tamaño fuente nombre", 6, 24, 10)

# --- FUNCIÓN: DIBUJAR TEXTO CENTRADO ---
def draw_centered_text(draw, text, y, font, image_width):
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (image_width - text_width) / 2
    draw.text((x, y), text, fill="black", font=font)
    return text_height

# --- GENERACIÓN DE ETIQUETAS ---
if archivo is not None:
    df = pd.read_excel(archivo)

    st.success(f"{len(df)} artículos cargados correctamente ✅")
    st.write(df.head())

    # --- PREVISUALIZACIÓN ---
    st.subheader("🔍 Previsualización de una etiqueta")

    muestra = df.iloc[0]
    sku = str(muestra["sku"])
    nombre = str(muestra["nombre"])
    url = str(muestra["url"])

    logo = Image.open(LOGO_PATH).convert("RGBA")

    # Crear una imagen de etiqueta
    etiqueta_px = (int(ancho_mm * 8), int(alto_mm * 8))  # Escala 8 px/mm para buena calidad
    img = Image.new("RGB", etiqueta_px, "white")
    draw = ImageDraw.Draw(img)

    # --- LOGO ---
    max_logo_w = etiqueta_px[0] * 0.7
    aspect_ratio = logo.height / logo.width
    logo_h = int(max_logo_w * aspect_ratio)
    logo_resized = logo.resize((int(max_logo_w), logo_h))
    logo_x = (etiqueta_px[0] - logo_resized.width) // 2
    img.paste(logo_resized, (logo_x, 10), logo_resized)

    # --- QR ---
    qr = qrcode.make(url)
    qr_size = int(min(etiqueta_px) * 0.35)
    qr = qr.resize((qr_size, qr_size))
    qr_x = (etiqueta_px[0] - qr_size) // 2
    qr_y = int(etiqueta_px[1] / 2.2)
    img.paste(qr, (qr_x, qr_y))

    # --- SKU y Nombre ---
    try:
        font_sku = ImageFont.truetype("arialbd.ttf", font_sku_size * 4)
        font_nombre = ImageFont.truetype("arial.ttf", font_nombre_size * 4)
    except:
        font_sku = ImageFont.load_default()
        font_nombre = ImageFont.load_default()

    text_y = qr_y + qr_size + 20
    text_y += draw_centered_text(draw, sku, text_y, font_sku, etiqueta_px[0]) + 10
    draw_centered_text(draw, nombre, text_y, font_nombre, etiqueta_px[0])

    st.image(img, caption="Vista previa de etiqueta generada")

    # --- GENERAR PDF ---
    if st.button("📄 Generar PDF con todas las etiquetas"):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        w_page, h_page = A4

        cols = int(w_page // (ancho_mm * mm))
        rows = int(h_page // (alto_mm * mm))
        x0, y0 = 10 * mm, h_page - alto_mm * mm - 10 * mm

        for i, row in df.iterrows():
            sku = str(row["sku"])
            nombre = str(row["nombre"])
            url = str(row["url"])

            # Crear etiqueta en memoria
            etiqueta = Image.new("RGB", etiqueta_px, "white")
            draw = ImageDraw.Draw(etiqueta)
            etiqueta.paste(logo_resized, (logo_x, 10), logo_resized)

            qr = qrcode.make(url)
            qr = qr.resize((qr_size, qr_size))
            etiqueta.paste(qr, (qr_x, qr_y))

            text_y = qr_y + qr_size + 20
            text_y += draw_centered_text(draw, sku, text_y, font_sku, etiqueta_px[0]) + 10
            draw_centered_text(draw, nombre, text_y, font_nombre, etiqueta_px[0])

            etiqueta_buf = BytesIO()
            etiqueta.save(etiqueta_buf, format="PNG")
            etiqueta_buf.seek(0)

            etiqueta_img = ImageReader(etiqueta_buf)

            col = i % cols
            fila = (i // cols) % rows
            x = 10 * mm + col * (ancho_mm * mm)
            y = h_page - (10 * mm + (fila + 1) * (alto_mm * mm))

            c.drawImage(etiqueta_img, x, y, ancho_mm * mm, alto_mm * mm)

            if (i + 1) % (cols * rows) == 0:
                c.showPage()

        c.save()
        buffer.seek(0)
        st.download_button("⬇️ Descargar etiquetas en PDF", buffer, "etiquetas_qr.pdf", mime="application/pdf")

else:
    st.info("📂 Cargá tu archivo Excel para comenzar.")
