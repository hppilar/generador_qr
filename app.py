import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw
import os
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_LEFT

styles = getSampleStyleSheet()
style = styles["Normal"]
style.fontName = "Helvetica"
style.fontSize = 7
style.alignment = TA_LEFT  # alineación a la izquierda
style.leading = 8  # altura de línea

# ----------------- Configuración de página -----------------
st.set_page_config(page_title="Generador de Etiquetas QR", layout="centered")

st.title("🏷️ Generador de etiquetas con código QR y logo")
st.write("Subí un archivo Excel con columnas: **SKU**, **Nombre**, **URL**")

# ----------------- Subida de Excel -----------------
archivo = st.file_uploader("Selecciona un archivo Excel (.xlsx)", type=["xlsx"])
logo_path = "logo.png"  # Logo en la raíz del repo

# ----------------- Plantillas -----------------
plantillas = {
    "Avery 3x8 (24 etiquetas)": {"cols": 3, "rows": 8},
    "Avery 4x10 (40 etiquetas)": {"cols": 4, "rows": 10},
    "Personalizada": None,
}

plantilla_seleccionada = st.selectbox("🧾 Selecciona la plantilla de etiquetas", list(plantillas.keys()))
if plantilla_seleccionada == "Personalizada":
    etiquetas_por_fila = st.number_input("Etiquetas por fila", 1, 6, 3)
    etiquetas_por_columna = st.number_input("Etiquetas por columna", 1, 12, 8)
else:
    etiquetas_por_fila = plantillas[plantilla_seleccionada]["cols"]
    etiquetas_por_columna = plantillas[plantilla_seleccionada]["rows"]

# ----------------- Procesamiento del Excel -----------------
if archivo:
    df = pd.read_excel(archivo)
    st.dataframe(df)

    # ----------------- Previsualización -----------------
    st.subheader("👁️ Previsualización de una etiqueta")
    ejemplo = df.iloc[0]
    sku = str(ejemplo.get("SKU", ""))
    nombre = str(ejemplo.get("Nombre", ""))
    url = str(ejemplo.get("URL", ""))

    # QR
    qr = qrcode.make(url).resize((150, 150))
    etiqueta_preview = Image.new("RGB", (350, 250), (245, 247, 250))
    draw = ImageDraw.Draw(etiqueta_preview)

    # Logo
    try:
        logo_img = Image.open(logo_path).convert("RGBA").resize((80, 80))
        etiqueta_preview.paste(logo_img, (10, 10), logo_img)
    except Exception:
        pass

    etiqueta_preview.paste(qr, (190, 30))
    draw.text((20, 200), f"SKU: {sku}", fill=(0, 0, 0))
    draw.text((20, 220), nombre[:40], fill=(0, 0, 0))
    st.image(etiqueta_preview, caption="Vista previa de la etiqueta", use_container_width=False)

    # ----------------- Botón Generar PDF -----------------
    if st.button("📄 Generar PDF de etiquetas"):
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4

        margen_x = 10 * mm
        margen_y = 15 * mm
        espacio_x = (width - 2 * margen_x) / etiquetas_por_fila
        espacio_y = (height - 2 * margen_y) / etiquetas_por_columna

        x_pos = 0
        y_pos = 0

        for i, row in df.iterrows():
            sku = str(row.get("SKU", ""))
            nombre = str(row.get("Nombre", ""))
            url = str(row.get("URL", ""))

            # QR
            qr = qrcode.make(url)
            qr_buffer = BytesIO()
            qr.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            qr_image = ImageReader(qr_buffer)

            # Coordenadas
            x = margen_x + x_pos * espacio_x
            y = height - margen_y - (y_pos + 1) * espacio_y

            # Fondo
            c.setFillColorRGB(0.96, 0.97, 0.99)
            c.rect(x, y, espacio_x - 5, espacio_y - 5, fill=True, stroke=False)

            # Logo
            if os.path.exists(logo_path):
                logo = ImageReader(logo_path)
                c.drawImage(logo, x + 5, y + 25, width=25*mm, height=15*mm, mask='auto')

            # Dibujar QR
            c.drawImage(qr_image, x + 25, y + 20, width=30*mm, height=30*mm)

            # Crear el texto SKU + Nombre
            texto = f"<b>{sku}</b> {nombre}"
            p = Paragraph(texto, style)
            p.wrapOn(c, espacio_x - 10, espacio_y / 2)  # ancho disponible dentro de la etiqueta
            p.drawOn(c, x + 5, y + 5)  # posición dentro de la etiqueta

            # Siguiente posición
            x_pos += 1
            if x_pos >= etiquetas_por_fila:
                x_pos = 0
                y_pos += 1
                if y_pos >= etiquetas_por_columna:
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
st.caption("Desarrollado por [Tu Empresa] — Generador de etiquetas QR automatizadas")



