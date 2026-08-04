"""
Conversión de fotografías/imágenes a PDF para DocConvert NCTS (Android).

Motor: Pillow (ya lo trae fpdf2 como dependencia, con receta madura y
probada en python-for-android -- a diferencia de lxml, Pillow SÍ compila
bien para Android). Cada imagen va en su propia página, ajustada al
tamaño de página elegido sin deformarse (letterbox: se centra dejando
márgenes si la proporción no coincide, nunca se recorta ni se estira).

Trade-off que debes conocer:
- No hace OCR ni detecta bordes de documento automáticamente (no es un
  "escáner inteligente" tipo CamScanner) -- toma la foto tal cual está.
- La compresión de "calidad" es JPEG estándar; para fotos ya comprimidas
  (típico de cámaras de celular) la reducción de tamaño tiene un límite
  real, no es magia.
"""

import os
from typing import Callable, List, Optional, Tuple

ProgressCallback = Optional[Callable[[str], None]]

PAGE_SIZES_MM = {
    "A4": (210.0, 297.0),
    "Carta": (215.9, 279.4),
}

QUALITY_JPEG = {
    "Baja": 45,
    "Media": 70,
    "Alta": 90,
}

# Al bajar la calidad también limitamos la resolución máxima que se
# incrusta en el PDF -- una foto de 12 MP a calidad "alta" ya pesa mucho
# por sí sola; esto evita PDFs de decenas de MB con muchas fotos.
MAX_DIMENSION_PX = {
    "Baja": 1000,
    "Media": 1600,
    "Alta": 2400,
}

MM_TO_PT = 72.0 / 25.4


class ConversionError(Exception):
    pass


def _mm_to_pt(mm: float) -> float:
    return mm * MM_TO_PT


def rotate_image_file(path: str, degrees: int = 90) -> None:
    """Rota una imagen 90/180/270 grados y la sobreescribe en el mismo archivo."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ConversionError(f"Falta la librería Pillow: {exc}")

    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)  # respeta orientación EXIF original primero
            rotated = img.rotate(-degrees, expand=True)
            rotated.save(path)
    except Exception as exc:
        raise ConversionError(f"No se pudo rotar la imagen: {exc}")


def get_image_dimensions(path: str) -> Optional[Tuple[int, int]]:
    """Devuelve (ancho, alto) en píxeles, o None si no se pudo leer la imagen."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def convert_images_to_pdf(
    image_paths: List[str],
    output_path: str,
    page_size: str = "Carta",
    quality: str = "Media",
    progress_cb: ProgressCallback = None,
) -> None:
    """
    Crea un único PDF con una imagen por página, en el orden dado por
    image_paths. Cada imagen se ajusta (sin deformar ni recortar) al
    tamaño de página elegido, manteniendo su propia orientación.
    """
    try:
        from PIL import Image, ImageOps
        from fpdf import FPDF
    except ImportError as exc:
        raise ConversionError(f"Faltan librerías necesarias: {exc}")

    if not image_paths:
        raise ConversionError("No hay imágenes seleccionadas.")

    if page_size not in PAGE_SIZES_MM:
        page_size = "Carta"
    if quality not in QUALITY_JPEG:
        quality = "Media"

    page_w_mm, page_h_mm = PAGE_SIZES_MM[page_size]
    jpeg_quality = QUALITY_JPEG[quality]
    max_dim = MAX_DIMENSION_PX[quality]

    pdf = FPDF(unit="mm")
    temp_files = []

    try:
        total = len(image_paths)
        for index, img_path in enumerate(image_paths):
            if progress_cb:
                progress_cb(f"Procesando imagen {index + 1} de {total}...")

            if not os.path.isfile(img_path):
                raise ConversionError(f"No se encontró la imagen: {os.path.basename(img_path)}")

            try:
                with Image.open(img_path) as img:
                    img = ImageOps.exif_transpose(img)  # corrige fotos "de lado" por EXIF
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")

                    # Limitar resolución según calidad elegida, preservando proporción.
                    img.thumbnail((max_dim, max_dim), Image.LANCZOS)

                    img_w_px, img_h_px = img.size
                    is_landscape = img_w_px > img_h_px

                    page_w = page_h_mm if is_landscape else page_w_mm
                    page_h = page_w_mm if is_landscape else page_h_mm

                    # Ajustar dentro de la página sin deformar (como "contain" en CSS).
                    img_ratio = img_w_px / img_h_px
                    page_ratio = page_w / page_h
                    if img_ratio > page_ratio:
                        draw_w = page_w
                        draw_h = page_w / img_ratio
                    else:
                        draw_h = page_h
                        draw_w = page_h * img_ratio

                    x = (page_w - draw_w) / 2
                    y = (page_h - draw_h) / 2

                    temp_path = f"{output_path}.tmp{index}.jpg"
                    img.save(temp_path, "JPEG", quality=jpeg_quality)
                    temp_files.append(temp_path)

                pdf.add_page(format=(page_w, page_h))
                pdf.image(temp_path, x=x, y=y, w=draw_w, h=draw_h)
            except ConversionError:
                raise
            except Exception as exc:
                raise ConversionError(
                    f"No se pudo procesar la imagen {os.path.basename(img_path)} "
                    f"(¿está dañada?): {exc}"
                )

        if progress_cb:
            progress_cb("Guardando PDF...")

        pdf.output(output_path)
    finally:
        for temp_path in temp_files:
            try:
                os.remove(temp_path)
            except Exception:
                pass

    if not os.path.isfile(output_path):
        raise ConversionError("La conversión finalizó pero no se generó el archivo PDF.")
