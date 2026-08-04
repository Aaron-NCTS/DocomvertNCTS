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


def detect_real_image_format(path: str) -> str:
    """
    Detecta el formato real de una imagen leyendo sus primeros bytes (no
    confía solo en la extensión del nombre, que puede venir mal o ausente
    desde un content:// URI de Google Fotos/WhatsApp/Drive/etc.).

    Regresa uno de: "jpeg", "png", "webp", "heic", "heif", "unknown".
    """
    try:
        with open(path, "rb") as f:
            header = f.read(32)
    except Exception:
        return "unknown"

    if header[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    # HEIC/HEIF: formato contenedor ISO-BMFF, con una caja "ftyp" que
    # declara el tipo real (heic, heix, hevc, heim, heis, mif1, msf1...).
    if header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevx"):
            return "heic"
        if brand in (b"mif1", b"msf1"):
            return "heif"
    return "unknown"


HEIC_MESSAGE = (
    "Este formato (HEIC/HEIF, típico de iPhone) todavía no es compatible: "
    "requiere una librería (libheif) que no se puede compilar de forma "
    "confiable para Android en este proyecto. Convierte la foto a JPG o "
    "PNG antes de agregarla (muchos celulares tienen esa opción al "
    "compartir la foto), o cambia el ajuste de la cámara a 'Más compatible'."
)


def validate_image_file(path: str) -> None:
    """
    Valida que un archivo sea una imagen realmente decodificable, usando
    el contenido real (no solo la extensión ni el MIME type que reporta
    el proveedor de archivos -- Google Fotos, WhatsApp, Drive, etc. a
    veces entregan MIME types genéricos o incorrectos).

    Lanza ConversionError con un mensaje específico si:
    - Es HEIC/HEIF (formato real detectado, pero no soportado -- ver honestidad
      arriba).
    - No es ninguno de los formatos que Pillow puede decodificar.
    - El archivo está dañado (Pillow no logra verificarlo).
    """
    real_format = detect_real_image_format(path)
    if real_format in ("heic", "heif"):
        raise ConversionError(HEIC_MESSAGE)

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ConversionError(f"Falta la librería Pillow: {exc}")

    try:
        with Image.open(path) as img:
            img.verify()
    except UnidentifiedImageError:
        raise ConversionError(
            "Ese archivo no es una imagen válida o está dañado "
            "(no se pudo decodificar su contenido)."
        )
    except Exception as exc:
        raise ConversionError(f"No se pudo verificar la imagen: {exc}")


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
