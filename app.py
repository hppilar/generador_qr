import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_CENTER
from PIL import Image
from reportlab.lib.styles import ParagraphStyle
import os

estilo_nombre = ParagraphStyle(
    "nombre",
    fontName="Helvetica-Bold",
    fontSize=max(8, min(14, ancho_etiqueta / 5)),  # 🔠 tamaño dinámico
    alignment=TA_CENTER,
    leading=12,
)

estilo_sku = ParagraphStyle(
    "sku",
    fontName="Helvetica",
    fontSize=max(6, min(10, ancho_etiqueta / 7)),  # 🔡 más chico
    alignment=TA_CENTER,
    leading=10,
)

# ----------------- CONFIGURACIÓN -----------------
st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")

st.title("🏷️ Generador de etiquetas QR personalizadas")
st.write("Subí un Excel con las columnas: **SKU**, **Nombre**, **URL**")

# ----------------- SUBIR ARCHIVO -----------------
archivo = st.file_uploader("Selecciona un archivo Excel (.xlsx)", type=["xlsx"])
logo_path = "logo.png"  # logo en la raíz del repo

# ----------------- PARÁMETROS DE ETIQUETA -----------------
st.subheader("⚙️ Configuración de la etiqueta (en milímetros)")

col1, col2, col3 = st.columns(3)
with col1:
    ancho_etiqueta = st.number_input("Ancho de etiqueta", min_value=40, max_value=150, value=60, step=5)
with col2:
    alto_etiqueta = st.number_input("Alto de etiqueta", min_value=50, max_value=150, value=80, step=5)
with col3:
    margen_pagina = st.number_input("Margen hoja (mm)", min_value=5, max_value=20, value=10, step=1)

# Calcular cantidad por hoja
cols_por_hoja = int((210 - 2 * margen_pagina) // ancho_etiqueta)
rows_por_hoja = int((297 - 2 * margen_pagina) // alto_etiqueta)
st.write(f"📄 Se imprimirán **{cols_por_hoja * rows_por_hoja} etiquetas por hoja (A4)** ({cols_por_hoja} × {rows_por_hoja})")

# ----------------- PROCESAR ARCHIVO -----------------
if archivo:
    df = pd.read_excel(archivo)
    st.dataframe(df)

    # --- PREVISUALIZACIÓN ---
    st.subheader("👁️ Previsualización de una etiqueta")

    ejemplo = df.iloc[0]
    sku = str(ejemplo.get("SKU", ""))
    nombre = str(ejemplo.get("Nombre", ""))
    url = str(ejemplo.get("URL", ""))

    # Generar QR
    qr = qrcode.make(url)
    qr_size_px = int((ancho_etiqueta * 3.78) * 0.6)  # 60% del ancho
    qr = qr.resize((qr_size_px, qr_size_px))

    etiqueta_img = Image.new("RGB", (int(ancho_etiqueta * 3.78), int(alto_etiqueta * 3.78)), (245, 247, 250))
    draw_y = 10

    # Logo centrado
    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        logo_w = int(ancho_etiqueta * 3.78 * 0.4)
        ratio = logo_img.width / logo_img.height
        logo_h = int(logo_w / ratio)
        logo_img = logo_img.resize((logo_w, logo_h))
        etiqueta_img.paste(logo_img, ((etiqueta_img.width - logo_w)//2, draw_y), logo_img)
        draw_y += logo_h + 10
    except Exception:
        draw_y += 30

    # QR centrado
    etiqueta_img.paste(qr, ((etiqueta_img.width - qr.width)//2, draw_y))
    draw_y += qr.height + 10

    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(etiqueta_img)
    font = ImageFont.load_default()
    draw.text((etiqueta_img.width/2, draw_y + 20), sku, fill=(0, 0, 0), anchor="mm")
    draw.text((etiqueta_img.width/2, draw_y), nombre[:40], fill=(0, 0, 0), anchor="mm")

    st.image(etiqueta_img, caption="Vista previa de etiqueta", use_container_width=False)

    # ----------------- GENERAR PDF -----------------
    if st.button("📄 Generar PDF de etiquetas"):
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4

        estilo = getSampleStyleSheet()["Normal"]
        estilo.alignment = TA_CENTER
        estilo.fontName = "Helvetica"
        estilo.fontSize = max(6, min(10, ancho_etiqueta / 8))
        estilo.leading = estilo.fontSize + 1

        qr_size_mm = ancho_etiqueta * 0.6
        logo_width_mm = ancho_etiqueta * 0.4
        logo_height_mm = logo_width_mm * 0.4

        x_pos = 0
        y_pos = 0

        for _, row in df.iterrows():
            sku = str(row.get("SKU", ""))
            nombre = str(row.get("Nombre", ""))
            url = str(row.get("URL", ""))

            x = margen_pagina * mm + x_pos * ancho_etiqueta * mm
            y = height - margen_pagina * mm - (y_pos + 1) * alto_etiqueta * mm

            # Fondo
            c.setFillColorRGB(0.96, 0.97, 0.99)
            c.rect(x, y, ancho_etiqueta * mm, alto_etiqueta * mm, fill=True, stroke=False)

            # Logo centrado arriba
            if os.path.exists(logo_path):
                logo = ImageReader(logo_path)
                c.drawImage(
                    logo,
                    x + (ancho_etiqueta * mm - logo_width_mm * mm) / 2,
                    y + alto_etiqueta * mm - logo_height_mm * mm - 5,
                    width=logo_width_mm * mm,
                    height=logo_height_mm * mm,
                    mask="auto"
                )

            # QR
            qr = qrcode.make(url)
            qr_buffer = BytesIO()
            qr.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            qr_image = ImageReader(qr_buffer)
            c.drawImage(
                qr_image,
                x + (ancho_etiqueta * mm - qr_size_mm * mm) / 2,
                y + (alto_etiqueta * mm - qr_size_mm * mm) / 2 - 10,
                width=qr_size_mm * mm,
                height=qr_size_mm * mm
            )

            # --- DIBUJAR SKU (debajo del nombre) ---
            p_sku = Paragraph(sku, estilo_sku)
            p_w2, p_h2 = p_sku.wrap(ancho_etiqueta * mm - 10, alto_etiqueta * mm)
            p_sku.drawOn(c, x + (ancho_etiqueta * mm - p_w2) / 2, y + 10 + p_h + 2)
            
            # --- DIBUJAR NOMBRE ---
            p_nombre = Paragraph(nombre, estilo_nombre)
            p_w, p_h = p_nombre.wrap(ancho_etiqueta * mm - 10, alto_etiqueta * mm)
            p_nombre.drawOn(c, x + (ancho_etiqueta * mm - p_w) / 2, y + 10)

            # Siguiente posición
            x_pos += 1
            if x_pos >= cols_por_hoja:
                x_pos = 0
                y_pos += 1
                if y_pos >= rows_por_hoja:
                    c.showPage()
                    y_pos = 0

        c.save()
        pdf_buffer.seek(0)

        st.success("✅ PDF generado correctamente")
        st.download_button(
            label="📥 Descargar etiquetas PDF",
            data=pdf_buffer,
            file_name="etiquetas_qr.pdf",
            mime="application/pdf"
        )

st.markdown("---")
st.caption("Desarrollado por NAN — Generador de etiquetas QR automatizadas")



