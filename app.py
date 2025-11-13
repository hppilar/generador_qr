import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import barcode
from barcode.writer import ImageWriter
import tempfile
import os

# ---------------- CONFIGURACIÓN GENERAL ----------------
st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")
st.title("🏷️ Generador de etiquetas QR + Código de Barras")

LOGO_PATH = "logo.png"

if not os.path.exists(LOGO_PATH):
    st.error("⚠️ No se encontró el archivo logo.png en la carpeta del proyecto.")
else:
    st.image(LOGO_PATH, width=120)

st.markdown("""
Subí tu archivo Excel con las columnas:
- **sku**
- **nombre**
- **url**
- **codigo_barras** (número EAN válido o secuencia numérica)
""")

archivo = st.file_uploader("📄 Cargar archivo Excel", type=["xlsx"])

# ---------------- PARÁMETROS DE ETIQUETA ----------------
st.sidebar.header("⚙️ Configuración de etiqueta")
ancho_mm = st.sidebar.number_input("Ancho (mm)", 40, 150, 60, 5)
alto_mm = st.sidebar.number_input("Alto (mm)", 40, 150, 80, 5)

font_sku_size = st.sidebar.number_input("Tamaño fuente SKU (negrita)", 6, 24, 12)
font_nombre_size = st.sidebar.number_input("Tamaño fuente nombre", 6, 24, 10)

# ---------------- FUNCIONES AUXILIARES ----------------
def draw_centered_text(draw, text, y, font, image_width):
    """Dibuja texto centrado horizontalmente y devuelve su altura"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (image_width - text_width) / 2
    draw.text((x, y), text, fill="black", font=font)
    return text_height

def generar_codigo_barras(codigo):
    """Genera imagen del código de barras a partir de un número"""
    if not codigo.isdigit():
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    try:
        ean = barcode.get("ean13", codigo.zfill(12), writer=ImageWriter())
        barcode_path = ean.save(tmp.name[:-4])
        img_barra = Image.open(f"{tmp.name[:-4]}.png").convert("RGB")
        return img_barra
    except Exception as e:
        print("Error generando código de barras:", e)
        return None
    finally:
        tmp.close()

def generar_etiqueta(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_size, font_nombre_size, logo):
    """Genera una etiqueta completa como imagen PIL"""
    etiqueta_px = (int(ancho_mm * 8), int(alto_mm * 8))
    img = Image.new("RGB", etiqueta_px, "white")
    draw = ImageDraw.Draw(img)

    # Logo
    max_logo_w = etiqueta_px[0] * 0.7
    aspect_ratio = logo.height / logo.width
    logo_h = int(max_logo_w * aspect_ratio)
    logo_resized = logo.resize((int(max_logo_w), logo_h))
    logo_x = (etiqueta_px[0] - logo_resized.width) // 2
    img.paste(logo_resized, (logo_x, 10), logo_resized)

    # QR
    qr = qrcode.make(url)
    qr_size = int(min(etiqueta_px) * 0.35)
    qr = qr.resize((qr_size, qr_size))
    qr_x = (etiqueta_px[0] - qr_size) // 2
    qr_y = int(etiqueta_px[1] * 0.3)
    img.paste(qr, (qr_x, qr_y))

    # Fuentes
    try:
        font_sku = ImageFont.truetype("arialbd.ttf", font_sku_size * 4)
        font_nombre = ImageFont.truetype("arial.ttf", font_nombre_size * 4)
    except:
        font_sku = ImageFont.load_default()
        font_nombre = ImageFont.load_default()

    # Texto
    y_text = qr_y + qr_size + 20
    h_sku = draw_centered_text(draw, sku, y_text, font_sku, etiqueta_px[0])
    y_text += h_sku + 10
    h_nombre = draw_centered_text(draw, nombre, y_text, font_nombre, etiqueta_px[0])
    y_text += h_nombre + 10

    # Código de barras
    barra_img = generar_codigo_barras(codigo_barras)
    if barra_img:
        barra_w = int(etiqueta_px[0] * 0.8)
        aspect = barra_img.height / barra_img.width
        barra_h = int(barra_w * aspect)
        barra_img = barra_img.resize((barra_w, barra_h))
        barra_x = (etiqueta_px[0] - barra_w) // 2
        barra_y = etiqueta_px[1] - barra_h - 10
        img.paste(barra_img, (barra_x, barra_y))

    return img


# ---------------- LÓGICA PRINCIPAL ----------------
if archivo is not None:
    df = pd.read_excel(archivo)
    st.success(f"{len(df)} artículos cargados correctamente ✅")
    st.write(df.head())

    logo = Image.open(LOGO_PATH).convert("RGBA")

    st.subheader("🔍 Previsualización de una etiqueta")
    muestra = df.iloc[0]
    img_preview = generar_etiqueta(
        str(muestra.get("sku", "")),
        str(muestra.get("nombre", "")),
        str(muestra.get("url", "")),
        str(muestra.get("codigo_barras", "")),
        ancho_mm, alto_mm, font_sku_size, font_nombre_size, logo
    )
    st.image(img_preview, caption="Vista previa de etiqueta generada")

    # --- PDF ---
    if st.button("📄 Generar PDF con todas las etiquetas"):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        w_page, h_page = A4

        cols = int(w_page // (ancho_mm * mm))
        rows = int(h_page // (alto_mm * mm))
        x0, y0 = 10 * mm, h_page - alto_mm * mm - 10 * mm

        for i, row in df.iterrows():
            etiqueta = generar_etiqueta(
                str(row.get("sku", "")),
                str(row.get("nombre", "")),
                str(row.get("url", "")),
                str(row.get("codigo_barras", "")),
                ancho_mm, alto_mm, font_sku_size, font_nombre_size, logo
            )

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
        st.download_button("⬇️ Descargar PDF con etiquetas", buffer, "etiquetas_qr.pdf", mime="application/pdf")

else:
    st.info("📂 Cargá tu archivo Excel para comenzar.")
