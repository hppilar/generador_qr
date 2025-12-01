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
import requests
from urllib.parse import urlparse
import re

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

st.set_page_config(page_title="Generador de etiquetas QR", layout="wide")

# Ruta fija del logo (archivo en la raíz del repo)
LOGO_PATH = "logo.png"

# Función para verificar si una URL es válida
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

# Función para cargar imagen desde URL
def load_image_from_url(url, timeout=5):
    try:
        if not is_valid_url(url):
            return None
            
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # Verificar si el contenido es una imagen
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            return None
            
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        logger.warning(f"Error al cargar imagen desde URL {url}: {e}")
        return None

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
def build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path, mostrar_codigo_qr=True, mostrar_codigo_barras=True, mostrar_logo=True, qr_error_correction="M"):
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
def generar_etiquetas_paralelo(df, cols, rows, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path, mostrar_codigo_qr, mostrar_codigo_barras, mostrar_logo, qr_error_correction):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_w, page_h = A4
    
    # Función para procesar una etiqueta individual
    def procesar_etiqueta(i, row):
        sku = str(row.get("sku",""))
        nombre = str(row.get("nombre",""))
        url = str(row.get("url",""))
        codigo_barras = str(row.get("codigo_barras","")) if "codigo_barras" in df.columns else ""
        
        img_label = build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, logo_path, mostrar_codigo_qr, mostrar_codigo_barras, mostrar_logo, qr_error_correction)
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

# Función para mostrar imagen con zoom
def mostrar_imagen_con_zoom(url, caption="", width=200):
    if not url or not is_valid_url(url):
        st.info("No hay imagen disponible")
        return
    
    try:
        # Cargar imagen desde URL
        img = load_image_from_url(url)
        if img is None:
            st.info("No se pudo cargar la imagen")
            return
        
        # Mostrar miniatura
        st.image(img, caption=caption, width=width)
        
        # Botón para ver imagen completa
        if st.button(f"Ver imagen completa", key=f"zoom_{url}"):
            st.session_state.zoom_image_url = url
            st.session_state.show_zoom = True
    except Exception as e:
        logger.warning(f"Error al mostrar imagen: {e}")
        st.info("No se pudo cargar la imagen")

# Función para mostrar diálogo de zoom
def mostrar_dialogo_zoom():
    if st.session_state.get("show_zoom", False) and st.session_state.get("zoom_image_url"):
        with st.expander("Vista ampliada", expanded=True):
            url = st.session_state.zoom_image_url
            img = load_image_from_url(url)
            if img:
                st.image(img, caption="Imagen ampliada", use_column_width=True)
            else:
                st.error("No se pudo cargar la imagen")
            
            if st.button("Cerrar vista ampliada"):
                st.session_state.show_zoom = False
                st.session_state.zoom_image_url = None
                st.experimental_rerun()

# Inicializar estado de sesión
if 'selected_items' not in st.session_state:
    st.session_state.selected_items = []
if 'show_zoom' not in st.session_state:
    st.session_state.show_zoom = False
if 'zoom_image_url' not in st.session_state:
    st.session_state.zoom_image_url = None

# Cargar datos desde Excel (para el modo masivo)
@st.cache_data
def load_data_from_excel_batch(archivo):
    try:
        df = pd.read_excel(archivo)
        # Mapear columnas a nombres estándar
        column_mapping = {
            'SKU': 'sku',
            'Articulo': 'nombre',
            'URL WEB': 'url',
            'Codigo barras': 'codigo_barras'
        }
        
        # Renombrar solo las columnas que existen en el mapeo
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)
        
        return df
    except Exception as e:
        st.error(f"Error leyendo Excel: {e}")
        logger.error(f"Error leyendo Excel: {e}")
        return None

# Cargar datos desde Excel (para el modo individual)
@st.cache_data
def load_data_from_excel_individual(archivo):
    try:
        df = pd.read_excel(archivo)
        # Mapear columnas a nombres estándar
        column_mapping = {
            'SKU': 'sku',
            'Nombre': 'nombre',
            'Codigo Barras': 'codigo_barras',
            'Rubro': 'rubro',
            'URL foto': 'imagen_url'
        }
        
        # Renombrar solo las columnas que existen en el mapeo
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)
        
        return df
    except Exception as e:
        st.error(f"Error leyendo Excel: {e}")
        logger.error(f"Error leyendo Excel: {e}")
        return None

# Título y logo
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=140)
    st.title("🏷️ Generador de etiquetas QR + código de barras")

# Selector de modo
modo = st.radio("Seleccionar modo de generación:", ["Masivo (Excel)", "Individual (Búsqueda)"], horizontal=True)

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

# Mostrar diálogo de zoom si está activo
mostrar_dialogo_zoom()

# Modo Masivo (Excel)
if modo == "Masivo (Excel)":
    st.markdown("""
    Subí un Excel con columnas: **SKU**, **Articulo**, **URL WEB**, **Codigo barras**.
    - SKU se dibuja *primero* (en negrita).
    - Luego Articulo.
    - Código de barras (si hay número válido) en la parte inferior.
    """)

    # --- Inputs
    archivo = st.file_uploader("Cargar Excel (.xlsx)", type=["xlsx"])

    # --- Flujo principal ---
    if archivo is None:
        st.info("Cargá tu archivo Excel para comenzar.")
    else:
        df = load_data_from_excel_batch(archivo)
        
        if df is not None:
            # comprobar columnas mínimas
            if not all(col in df.columns for col in ["sku","nombre","url"]):
                st.error("El Excel debe contener al menos las columnas: SKU, Articulo, URL WEB")
                st.stop()

            st.success(f"{len(df)} filas leídas")

            # Previsualización de la primera fila
            st.subheader("Previsualización (fila 1)")
            first = df.iloc[0]
            sku = str(first.get("sku",""))
            nombre = str(first.get("nombre",""))
            url = str(first.get("url",""))
            codigo_barras = str(first.get("codigo_barras","")) if "codigo_barras" in df.columns else ""

            img_preview = build_label_image(sku, nombre, url, codigo_barras, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH, mostrar_codigo_qr, mostrar_codigo_barras, mostrar_logo, qr_error_correction)
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
                        buffer = generar_etiquetas_paralelo(df, cols, rows, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH, mostrar_codigo_qr, mostrar_codigo_barras, mostrar_logo, qr_error_correction)
                        
                        elapsed_time = time.time() - start_time
                        status_text.text(f"PDF generado en {elapsed_time:.2f} segundos")
                        progress_bar.progress(100)
                        
                        st.success("PDF generado ✅")
                        st.download_button("Descargar etiquetas (PDF)", buffer, file_name="etiquetas_qr.pdf", mime="application/pdf")
                    except Exception as e:
                        st.error(f"Error al generar PDF: {e}")
                        logger.error(f"Error al generar PDF: {e}")

# Modo Individual (Búsqueda)
else:
    st.markdown("""
    Buscá artículos por diferentes criterios para generar etiquetas individuales.
    Podés buscar por **SKU**, **Nombre**, **Código de Barras** o **Rubro**.
    """)
    
    # Primero, necesitamos cargar los datos desde un archivo Excel
    archivo_base = st.file_uploader("Cargar base de datos (.xlsx)", type=["xlsx"], key="base_datos")
    
    if archivo_base is None:
        st.info("Cargá tu archivo Excel con la base de datos para comenzar.")
    else:
        df = load_data_from_excel_individual(archivo_base)
        
        if df is not None:
            ### CORRECCIÓN: Validación de columnas mínimas para el modo individual ###
            # comprobar columnas mínimas (solo SKU y Nombre son obligatorios aquí)
            if not all(col in df.columns for col in ["sku","nombre"]):
                st.error("El Excel de la base de datos debe contener al menos las columnas: SKU, Nombre")
                st.stop()
            
            st.success(f"Base de datos cargada: {len(df)} artículos")

            # Sección de búsqueda
            st.subheader("Búsqueda de artículos")
            
            # Columnas para los campos de búsqueda
            col1, col2 = st.columns(2)
            
            with col1:
                # Búsqueda por SKU
                sku_busqueda = st.text_input("Buscar por SKU", key="sku_search")
                
                # Búsqueda por Código de Barras
                codigo_busqueda = st.text_input("Buscar por Código de Barras", key="codigo_search")
                
            with col2:
                # Búsqueda por Nombre
                nombre_busqueda = st.text_input("Buscar por Nombre", key="nombre_search")
                
                # Búsqueda por Rubro (si existe la columna)
                if "rubro" in df.columns:
                    rubros = df["rubro"].dropna().unique().tolist()
                    rubro_seleccionado = st.selectbox("Buscar por Rubro", [""] + rubros, key="rubro_search")
                else:
                    rubro_seleccionado = ""
            
            # Botón de búsqueda
            if st.button("Buscar"):
                # Filtrar según los criterios
                resultados = df.copy()
                
                if sku_busqueda:
                    resultados = resultados[resultados["sku"].astype(str).str.contains(sku_busqueda, case=False, na=False)]
                
                if codigo_busqueda and "codigo_barras" in resultados.columns:
                    resultados = resultados[resultados["codigo_barras"].astype(str).str.contains(codigo_busqueda, case=False, na=False)]
                
                if nombre_busqueda:
                    resultados = resultados[resultados["nombre"].astype(str).str.contains(nombre_busqueda, case=False, na=False)]
                
                if rubro_seleccionado:
                    resultados = resultados[resultados["rubro"] == rubro_seleccionado]
                
                # Guardar resultados en el estado de sesión
                st.session_state.search_results = resultados.reset_index(drop=True)
            
            # Mostrar resultados de búsqueda
            if "search_results" in st.session_state and len(st.session_state.search_results) > 0:
                st.subheader(f"Resultados de búsqueda ({len(st.session_state.search_results)})")
                
                # Mostrar resultados en un formato más visual
                for i, row in st.session_state.search_results.iterrows():
                    col_img, col_info, col_btn = st.columns([1, 3, 1])
                    
                    with col_img:
                        # Mostrar imagen si existe la columna imagen_url y la celda no está vacía
                        if "imagen_url" in row and pd.notna(row["imagen_url"]):
                            mostrar_imagen_con_zoom(row["imagen_url"], width=100)
                        else:
                            st.info("Sin imagen")
                    
                    with col_info:
                        sku = str(row.get("sku", ""))
                        nombre = str(row.get("nombre", ""))
                        codigo_barras = str(row.get("codigo_barras", "")) if "codigo_barras" in row else ""
                        rubro = str(row.get("rubro", "")) if "rubro" in row else ""
                        
                        st.write(f"**SKU:** {sku}")
                        st.write(f"**Nombre:** {nombre}")
                        if codigo_barras:
                            st.write(f"**Código de Barras:** {codigo_barras}")
                        if rubro:
                            st.write(f"**Rubro:** {rubro}")
                    
                    with col_btn:
                        # Botón para agregar a la lista de selección
                        if st.button("Agregar", key=f"add_{i}"):
                            # Verificar si ya está en la lista
                            if sku not in [item["sku"] for item in st.session_state.selected_items]:
                                st.session_state.selected_items.append({
                                    "sku": sku,
                                    "nombre": nombre,
                                    # El campo 'url' para el QR quedará vacío, ya que no existe en este archivo
                                    "url": "", 
                                    "codigo_barras": codigo_barras,
                                    "imagen_url": str(row["imagen_url"]) if "imagen_url" in row and pd.notna(row["imagen_url"]) else "",
                                    "rubro": rubro
                                })
                                st.success(f"Artículo {sku} agregado a la lista")
                            else:
                                st.warning(f"El artículo {sku} ya está en la lista")
            
            # Mostrar lista de artículos seleccionados
            if len(st.session_state.selected_items) > 0:
                st.subheader(f"Artículos seleccionados ({len(st.session_state.selected_items)})")
                
                # Crear un DataFrame con los artículos seleccionados
                df_selected = pd.DataFrame(st.session_state.selected_items)
                
                # Mostrar tabla con los artículos seleccionados
                for i, item in enumerate(st.session_state.selected_items):
                    col_img, col_info, col_btn = st.columns([1, 3, 1])
                    
                    with col_img:
                        # Mostrar imagen si existe
                        if item["imagen_url"]:
                            mostrar_imagen_con_zoom(item["imagen_url"], width=100)
                        else:
                            st.info("Sin imagen")
                    
                    with col_info:
                        st.write(f"**SKU:** {item['sku']}")
                        st.write(f"**Nombre:** {item['nombre']}")
                        if item["codigo_barras"]:
                            st.write(f"**Código de Barras:** {item['codigo_barras']}")
                        if item["rubro"]:
                            st.write(f"**Rubro:** {item['rubro']}")
                    
                    with col_btn:
                        # Botón para eliminar de la lista
                        if st.button("Eliminar", key=f"remove_{i}"):
                            st.session_state.selected_items.pop(i)
                
                # Previsualización de la primera etiqueta seleccionada
                st.subheader("Previsualización de etiqueta")
                first_selected = st.session_state.selected_items[0]
                
                img_preview = build_label_image(
                    first_selected["sku"], 
                    first_selected["nombre"], 
                    first_selected["url"],  # Este será un string vacío
                    first_selected["codigo_barras"], 
                    ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH,
                    mostrar_codigo_qr, mostrar_codigo_barras, mostrar_logo, qr_error_correction
                )
                st.image(img_preview, width=min(400, img_preview.width))
                
                # Botón para generar PDF
                if st.button("Generar PDF con artículos seleccionados"):
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
                            buffer = generar_etiquetas_paralelo(
                                df_selected, cols, rows, ancho_mm, alto_mm, font_sku_pt, font_nombre_pt, LOGO_PATH,
                                mostrar_codigo_qr, mostrar_codigo_barras, mostrar_logo, qr_error_correction
                            )
                            
                            elapsed_time = time.time() - start_time
                            status_text.text(f"PDF generado en {elapsed_time:.2f} segundos")
                            progress_bar.progress(100)
                            
                            st.success("PDF generado ✅")
                            st.download_button("Descargar etiquetas (PDF)", buffer, file_name="etiquetas_qr.pdf", mime="application/pdf")
                        except Exception as e:
                            st.error(f"Error al generar PDF: {e}")
                            logger.error(f"Error al generar PDF: {e}")
            else:
                st.info("No hay artículos seleccionados. Realizá una búsqueda y agregá artículos a la lista.")

# Informar sobre dependencias
if not BARCODE_AVAILABLE:
    st.info("La librería 'python-barcode' no está instalada: los códigos de barra no se generarán. "
            "Añadila a requirements.txt si querés esa función.")

