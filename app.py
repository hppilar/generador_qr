import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_CENTER
from PIL import Image, ImageDraw, ImageFont
import os

# barcode (python-barcode)
try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except Exception:
    BARCODE_AVAILABLE = False

# ----------------- CONFIG -----------------
st.set_page_config(page_title="Generador de etiquetas QR", layout="centered")
st.title("🏷️ Generador profesional de etiquetas con QR y código de barras")

st.write("Subí un Excel con las columnas: **SKU**, **Nombre**, **URL**, **CodigoBarra** (numérico).")
st.write("Si no tenés `CodigoBarra`, podés dejar esa columna vacía o con secuencias numéricas.")

# ----------------- SUBIR EXCEL & LOGO -----------------
archivo = st.file_uploader("Selecciona un archivo Excel (.xlsx)", type=["xlsx"])
logo_path = "logo.png"  # Pon aquí tu logo en la raíz del repo

# ----------------- CONFIG ETIQUETA (mm) -----------------
st.subheader("⚙️ Configuración de etiqueta (medidas en mm)")

col1, col2, col3 = st.columns(3)
with col1:
    ancho_etiqueta = st.number_input("Ancho etiqueta (mm)", min_value=30, max_value=150, value=60, step=1)
with col2:
    alto_etiqueta = st.number_input("Alto etiqueta (mm)", min_value=30, max_value=150, value=80, step=1)
with col3:
    margen_pagina = st.number_input("Margen hoja (mm)", min_value=5, max_value=30, value=10, step=1)

# límites/validaciones
if alto_etiqueta > 150:
    st.warning("El alto máximo permitido es 150 mm. Se ajustará a 150 mm.")
    alto_etiqueta = 150

# Ajustes visuales: control manual de tamaños de fuente
st.subheader("🔤 Ajustes de tipografía")
coln1, coln2 = st.columns(2)
with coln1:
    font_size_nombre = st.number_input("Tamaño fuente Nombre (pt)", min_value=6, max_value=36, value=int(max(8, min(14, ancho_etiqueta // 4))))
with coln2:
    font_size_sku = st.number_input("Tamaño fuente SKU (pt)", min_value=6, max_value=24, value=int(max(6, min(10, ancho_etiqueta // 6))))

# Validación mínima para QR: definimos un QR mínimo (en mm)
QR_MIN_MM = 18  # arbitrario pero razonable
# Calculamos tamaño QR propuesto en mm (será 60% del ancho por defecto)
qr_propuesto_mm = max(QR_MIN_MM, ancho_etiqueta * 0.6)
if ancho_etiqueta < qr_propuesto_mm:
    st.error(f"El ancho de la etiqueta ({ancho_etiqueta} mm) es menor al ancho mínimo del QR ({qr_propuesto_mm:.0f} mm). Aumentá el ancho.")
    st.stop()

# Cantidad por hoja
cols_por_hoja = int((210 - 2 * margen_pagina) // ancho_etiqueta)
rows_por_hoja = int((297 - 2 * margen_pagina) // alto_etiqueta)
if cols_por_hoja < 1 or rows_por_hoja < 1:
    st.error("Con ese tamaño de etiqueta y márgenes no cabe ninguna etiqueta en A4. Ajustá medidas/márgenes.")
    st.stop()

st.write(f"📄 Se imprimirán **{cols_por_hoja * rows_por_hoja}** etiquetas por hoja (A4): {cols_por_hoja} × {rows_por_hoja}")

# ----------------- PROCESAR ARCHIVO -----------------
if archivo:
    try:
        df = pd.read_excel(archivo)
    except Exception as e:
        st.error(f"Error leyendo Excel: {e}")
        st.stop()

    # Comprobar columnas mínimas
    for col in ["SKU", "Nombre", "URL"]:
        if col not in df.columns:
            st.error(f"Falta la columna obligatoria: '{col}' en tu Excel.")
            st.stop()

    # si no existe CodigoBarra, lo creamos si el usuario quiere
    if "CodigoBarra" not in df.columns:
        st.warning("No se encontró la columna 'CodigoBarra'. Podés generar secuencia automática.")
        if st.button("Generar secuencia automática en 'CodigoBarra'"):
            df["CodigoBarra"] = [str(100000000000 + i) for i in range(len(df))]  # ejemplo: 12 dígitos comenzando en 100...
            st.success("Secuencia generada en columna 'CodigoBarra'.")

    st.dataframe(df.head(50))

    # ----------------- PREVISUALIZACIÓN -----------------
    st.subheader("👁️ Previsualización de una etiqueta (vista aproximada)")

    ejemplo = df.iloc[0]
    sku = str(ejemplo.get("SKU", ""))
    nombre = str(ejemplo.get("Nombre", ""))
    url = str(ejemplo.get("URL", ""))
    codigo_barra = str(ejemplo.get("CodigoBarra", ""))

    # Tamaños en pixeles para vista previa (PIL) — factor approx: 3.78 px por mm
    MM_TO_PX = 3.78
    w_px = int(ancho_etiqueta * MM_TO_PX)
    h_px = int(alto_etiqueta * MM_TO_PX)
    preview = Image.new("RGB", (w_px, h_px), (245, 247, 250))

    draw = ImageDraw.Draw(preview)

    current_y = 5

    # LOGO: centrado arriba
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_w_px = int(w_px * 0.5)  # logo ocupa 50% del ancho en preview
            ratio = logo_img.width / logo_img.height
            logo_h_px = int(logo_w_px / ratio)
            logo_img = logo_img.resize((logo_w_px, logo_h_px))
            preview.paste(logo_img, ((w_px - logo_w_px) // 2, current_y), logo_img)
            current_y += logo_h_px + 5
        except Exception:
            pass
    else:
        current_y += 10

    # QR: centrado
    qr_size_px = int(min(w_px * 0.75, h_px * 0.45))  # fit mid area
    qr_img = qrcode.make(url).resize((qr_size_px, qr_size_px))
    preview.paste(qr_img, ((w_px - qr_size_px) // 2, current_y))
    current_y += qr_size_px + 5

    # SKU
    sku_w = draw.textlength(sku, font=font_sku)
    draw.text(((w_px - sku_w) // 2, current_y), sku, font=font_sku, fill=(0,0,0))
    current_y += font_sku.getsize(sku)[1] + 4
    
    # Nombre centrado (ajustar a varias líneas si hace falta)
    try:
        font_nombre = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size_nombre)
    except Exception:
        font_nombre = ImageFont.load_default()
    try:
        font_sku = ImageFont.truetype("DejaVuSans.ttf", font_size_sku)
    except Exception:
        font_sku = ImageFont.load_default()

 
    # dibujar nombre con wrap
    def draw_centered_wrapped_text(img_draw, text, x_center, y_start, font, max_width):
        words = text.split()
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            w_px = img_draw.textlength(test, font=font)
            if w_px <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        h = 0
        for i, line in enumerate(lines):
            w_line = img_draw.textlength(line, font=font)
            img_draw.text((x_center - w_line/2, y_start + h), line, font=font, fill=(0,0,0))
            h += font.getsize(line)[1] + 2
        return h

    max_text_w = int(w_px * 0.9)
    h_name = draw_centered_wrapped_text(draw, nombre, w_px//2, current_y, font_nombre, max_text_w)
    current_y += h_name + 3


    # Código de barras preview (si disponible y barcode lib instalada)
    if codigo_barra and BARCODE_AVAILABLE:
        try:
            barcode_obj = Code128(codigo_barra, writer=ImageWriter())
            bp = BytesIO()
            barcode_obj.write(bp, {"module_height": 8.0, "font_size": 10, "text_distance": 1.0})
            bp.seek(0)
            bar_img = Image.open(bp).convert("RGB")
            # redimensionar para ancho de etiqueta
            max_bar_w = int(w_px * 0.9)
            ratio = bar_img.width / bar_img.height
            new_h = int(max_bar_w / ratio)
            bar_img = bar_img.resize((max_bar_w, new_h))
            preview.paste(bar_img, ((w_px - max_bar_w)//2, current_y))
            current_y += new_h + 2
        except Exception:
            pass
    elif codigo_barra and not BARCODE_AVAILABLE:
        draw.text((10, current_y), "python-barcode no instalado: preview no disponible", fill=(150,0,0))
        current_y += 12

    st.image(preview, caption="Vista previa aproximada (no exacta a PDF)", use_column_width=False)

    # ----------------- GENERAR PDF -----------------
    if st.button("📄 Generar PDF de etiquetas"):
        # PDF buffer
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        page_w, page_h = A4

        # Estilos para texto en PDF
        estilo_nombre = ParagraphStyle(
            "nombre",
            fontName="Helvetica-Bold",
            fontSize=font_size_nombre,
            alignment=TA_CENTER,
            leading=font_size_nombre + 2
        )
        estilo_sku = ParagraphStyle(
            "sku",
            fontName="Helvetica",
            fontSize=font_size_sku,
            alignment=TA_CENTER,
            leading=font_size_sku + 2
        )

        # tamaños en mm
        qr_size_mm = max(QR_MIN_MM, ancho_etiqueta * 0.6)
        logo_w_mm = ancho_etiqueta * 0.5  # logo ocupa 50% del ancho
        logo_h_mm = logo_w_mm * 0.5  # aproximación (se ajustará por aspect ratio)

        x_idx = 0
        y_idx = 0

        for idx, row in df.iterrows():
            sku = str(row.get("SKU", ""))
            nombre = str(row.get("Nombre", ""))
            url = str(row.get("URL", ""))
            codigo_barra = str(row.get("CodigoBarra", ""))

            # coordenadas de la etiqueta en mm -> puntos
            x_mm = margen_pagina + x_idx * ancho_etiqueta
            y_mm = (297 - margen_pagina) - (y_idx + 1) * alto_etiqueta

            x_pt = x_mm * mm
            y_pt = y_mm * mm
            ancho_pt = ancho_etiqueta * mm
            alto_pt = alto_etiqueta * mm

            # Fondo (opcional)
            c.setFillColorRGB(0.96, 0.97, 0.99)
            c.rect(x_pt, y_pt, ancho_pt, alto_pt, fill=True, stroke=False)

            # Dibujar logo centrado arriba (usamos ImageReader automático)
            if os.path.exists(logo_path):
                try:
                    logo_reader = ImageReader(logo_path)
                    # read actual size to preserve aspect ratio
                    pil_logo = Image.open(logo_path)
                    ratio = pil_logo.width / pil_logo.height if pil_logo.height != 0 else 1
                    logo_w_use_mm = logo_w_mm
                    logo_h_use_mm = logo_w_use_mm / ratio if ratio != 0 else logo_w_use_mm * 0.5
                    # posicion: centrado horizontal, en la parte superior con margen 3mm
                    c.drawImage(
                        logo_reader,
                        x_pt + (ancho_pt - logo_w_use_mm * mm) / 2,
                        y_pt + alto_pt - logo_h_use_mm * mm - (3 * mm),
                        width=logo_w_use_mm * mm,
                        height=logo_h_use_mm * mm,
                        mask='auto'
                    )
                    logo_bottom_y = y_pt + alto_pt - logo_h_use_mm * mm - (3 * mm)
                except Exception:
                    logo_bottom_y = y_pt + alto_pt - (5 * mm)
            else:
                logo_bottom_y = y_pt + alto_pt - (5 * mm)

            # Dibujar QR centrado (debajo del logo)
            qr_size_use_mm = min(qr_size_mm, ancho_etiqueta * 0.85)  # evitar pasarse del ancho
            # generar QR
            qr_img = qrcode.make(url)
            qr_buf = BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            qr_reader = ImageReader(qr_buf)

            # calcular posición del QR: centrado horizontal, situado un poco debajo del logo
            # colocamos su centro a una posición intermedia
            qr_x = x_pt + (ancho_pt - qr_size_use_mm * mm) / 2
            # poner QR debajo del logo_bottom_y con separación 4 mm
            qr_y = logo_bottom_y - qr_size_use_mm * mm - (4 * mm)
            # si no hay logo, ponemos QR más centrado verticalmente
            if qr_y < y_pt + alto_pt * 0.35:
                # fallback: colocar QR en el centro vertical superior
                qr_y = y_pt + alto_pt * 0.5 - qr_size_use_mm * mm / 2

            c.drawImage(qr_reader, qr_x, qr_y, width=qr_size_use_mm * mm, height=qr_size_use_mm * mm)

            # Texto (Nombre) centrado: dibujarlo inmediatamente debajo del QR
            # reservamos un área para el texto
            text_area_top = qr_y - (3 * mm)
            text_area_height = (text_area_top - y_pt) * 0.6  # espacio aproximado por encima del barcode
            # pero vamos a dibujar el texto cerca del medio-bajo de la etiqueta
            # mejor calculamos Y para el texto: un poco por encima del área de barcode final
            # Dibujamos nombre y sku en la parte central-baja
            text_block_y = qr_y - (8 * mm)

            # SKU
            p_sku = Paragraph(sku, estilo_sku)
            p_w2, p_h2 = p_sku.wrap(ancho_pt - (6 * mm), 50*mm)
            p_sku.drawOn(c, x_pt + (ancho_pt - p_w2) / 2, text_block_y - p_h - p_h2 - (2 * mm))
            
            # Nombre (Paragraph)
            p_nombre = Paragraph(nombre, estilo_nombre)
            p_w, p_h = p_nombre.wrap(ancho_pt - (6 * mm), 100*mm)
            # colocamos el bloque centrado, si p_h es demasiado grande se irá a varias lineas
            p_nombre.drawOn(c, x_pt + (ancho_pt - p_w) / 2, text_block_y - p_h)

            # Código de barras en la parte inferior de la etiqueta (si código disponible)
            if codigo_barra and BARCODE_AVAILABLE:
                try:
                    barcode_obj = Code128(codigo_barra, writer=ImageWriter())
                    bp = BytesIO()
                    # ajustar tamaño del barcode según ancho etiqueta
                    module_height = max(6.0, (alto_etiqueta * 0.12))  # heurística
                    writer_opts = {
                        "module_height": module_height,
                        "font_size": 8,
                        "text_distance": 1.0,
                        "quiet_zone": 2.0,
                    }
                    barcode_obj.write(bp, writer_opts)
                    bp.seek(0)
                    bar_img = Image.open(bp)
                    bar_reader = ImageReader(bar_img)
                    # dimensionar el barcode para que ocupe ~90% del ancho
                    bar_target_w_mm = ancho_etiqueta * 0.9
                    # compute height preserving ratio
                    ratio = bar_img.width / bar_img.height if bar_img.height != 0 else 4
                    bar_target_h_mm = bar_target_w_mm / ratio
                    # dibujar en la parte inferior con margen 3mm
                    bar_x = x_pt + (ancho_pt - bar_target_w_mm * mm) / 2
                    bar_y = y_pt + 3 * mm
                    c.drawImage(bar_reader, bar_x, bar_y, width=bar_target_w_mm * mm, height=bar_target_h_mm * mm)
                except Exception as e:
                    # si falla el barcode no detener todo; podemos mostrar texto en su lugar
                    st.warning(f"No se pudo generar barcode para fila {idx}: {e}")

            # Next position
            x_idx += 1
            if x_idx >= cols_por_hoja:
                x_idx = 0
                y_idx += 1
                if y_idx >= rows_por_hoja:
                    c.showPage()
                    y_idx = 0

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
st.caption("Diseñado por NAN — Personalizá el diseño modificando las opciones.")


