import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Generador de Etiquetas QR", layout="centered")

st.markdown("""
<style>
    .main {
        background-color: #f5f7fa;
        background-image: linear-gradient(180deg, #f9fbff 0%, #eef2f8 100%);
        border-radius: 10px;
        padding: 2rem;
    }
    h1 {
        text-align: center;
        color: #2b5876;
    }
    .stButton>button {
        background-color: #2b5876;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 0.6rem 1.2rem;
    }
    .stButton>button:hover {
        background-color: #1e3c54;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏷️ Generador de etiquetas con código QR y logo")

st.write("Subí tu archivo Excel con las columnas: **SKU**, **Nombre**, **URL**")

# --- SUBIR ARCHIVO ---
archivo = st.file_uploader("Seleccioná un archivo Excel", type=["xlsx"])
logo_path = "logo.png"  # Tu logo (mismo directorio que el script)

# --- PLANTILLAS DISPONIBLES ---
plantillas = {
    "Avery 3x8 (24 etiquetas)": {"cols": 3, "rows": 8},
    "Avery 4x10 (40 etiquetas pequeñas)": {"cols": 4, "rows": 10},
    "Personalizada": None,
}

plantilla_seleccionada = st.selectbox("🧾 Seleccioná la plantilla de etiquetas", list(plantillas.keys()))
if plantilla_seleccionada == "Personalizada":
    etiquetas_por_fila = st.number_input("Etiquetas por fila", 1, 6, 3)
    etiquetas_por_columna = st.number_input("Etiquetas por columna", 1, 12, 8)
else:
    etiquetas_por_fila = plantillas[plantilla_seleccionada]["cols"]
    etiquetas_por_columna = plantillas[plantilla_seleccionada]["rows"]

if archivo:
    df = pd.read_excel(archivo)
    st.dataframe(df)

    # --- PREVISUALIZACIÓN DE ETIQUETA ---
    st.subheader("👁️ Previsualización de ejemplo")

    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        logo_img = logo_img.resize((80, 80))
    except Exception:
        logo_img = None

    # Toma el primer artículo como muestra
    ejemplo = df.iloc[0]
    sku = str(ejemplo.get("SKU", ""))
    nombre = str(ejemplo.get("Nombre", ""))
    url = str(ejemplo.get("URL", ""))

    # Crear QR
    qr = qrcode.make(url)
    qr = qr.resize((150, 150))

    etiqueta = Image.new("RGB", (350, 250), (245, 247, 250))
    draw = ImageDraw.Draw(etiqueta)

    if logo_img:
        etiqueta.paste(logo_img, (10, 10), logo_img)

    etiqueta.paste(qr, (190, 30))

    font_path = None  # Usará fuente por defecto
    draw.text((20, 200), f"SKU: {sku}", fill=(0, 0, 0))
    draw.text((20, 220), nombre[:40], fill=(0, 0, 0))

    st.image(etiqueta, caption="Vista previa de una etiqueta", use_container_width=False)

    if st.button("📄 Generar PDF de etiquetas"):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
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

            qr = qrcode.make(url)
            qr_buffer = BytesIO()
            qr.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)

            x = margen_x + x_pos * espacio_x
            y = height - margen_y - (y_pos + 1) * espacio_y

            # Fondo etiqueta
            c.setFillColorRGB(0.96, 0.97, 0.99)
            c.rect(x, y, espacio_x - 5, espacio_y - 5, fill=True, stroke=False)
            
            # ✅ Convertir BytesIO en objeto compatible
            qr_image = ImageReader(qr_buffer)
            
            # Logo en cada etiqueta
            try:
                logo = ImageReader(logo_path)
                c.drawImage(logo, x + 5, y + 35, width=15*mm, height=15*mm, mask='auto')
            except Exception:
                pass

            # QR
            c.drawImage(qr_buffer, x + 25, y + 20, width=35*mm, height=35*mm)

            # Texto SKU y nombre
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(x + espacio_x / 2, y + 12, f"{sku}")
            c.setFont("Helvetica", 9)
            c.drawCentredString(x + espacio_x / 2, y + 4, nombre[:45])

            # Manejo de posición
            x_pos += 1
            if x_pos >= etiquetas_por_fila:
                x_pos = 0
                y_pos += 1
                if y_pos >= etiquetas_por_columna:
                    c.showPage()
                    y_pos = 0

        c.save()
        buffer.seek(0)

        st.success("✅ PDF generado correctamente.")
        st.download_button(
            label="Descargar etiquetas PDF",
            data=buffer,
            file_name="etiquetas_qr.pdf",
            mime="application/pdf"
        )

st.markdown("---")
st.caption("Desarrollado por [Tu Empresa] — Generador de etiquetas QR automatizadas")

