"""
Conversión PDF -> Word para la versión móvil (Android) de DocConvert NCTS.

Motor: pypdf + docx_lite (nuestro propio escritor de .docx con la librería
estándar). Se eligió pypdf en vez de pdfminer.six porque pdfminer.six
depende de `cryptography` (extensión nativa en Rust/C sin build para
Android), y en vez de pdf2docx/PyMuPDF (motor de escritorio) porque tampoco
compila para Android. Se usa `docx_lite` en vez de `python-docx` porque
python-docx depende de `lxml`, que resultó imposible de compilar de forma
confiable para Android en este entorno (ver docx_lite.py para el detalle).

Trade-off que debes conocer: pypdf entrega el texto línea por línea, sin
información de bloques/párrafos como sí daba pdf2docx o pdfminer. Para
reconstruir párrafos se usa una heurística simple basada en puntuación
(si una línea termina en . ! ? : ; se asume fin de párrafo). Funciona bien
para texto corrido (cartas, reportes, contratos), pero:
  - No reconstruye tablas como tablas (el contenido aparece como texto suelto).
  - Puede unir o separar párrafos de forma incorrecta en casos raros
    (encabezados sin puntuación al final, líneas cortas, etc.).
"""

import os
import re
from typing import Callable, Optional

import docx_lite

ProgressCallback = Optional[Callable[[str], None]]

_CID_PATTERN = re.compile(r"\(cid:\d+\)")
_SENTENCE_END = (".", "!", "?", ":", ";")


class ConversionError(Exception):
    pass


def has_selectable_text(input_path: str, sample_pages: int = 3) -> bool:
    """Heurística rápida: revisa si las primeras páginas tienen texto extraíble."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(input_path)
        pages_to_check = min(sample_pages, len(reader.pages))
        text = ""
        for i in range(pages_to_check):
            text += reader.pages[i].extract_text() or ""
        return len(text.strip()) > 20
    except Exception:
        return True  # asumir que sí tiene texto y dejar que el motor lo intente


def _clean_line(line: str) -> str:
    """Limpia artefactos de glifos sin mapeo Unicode (típico en viñetas de PDFs generados)."""
    line = _CID_PATTERN.sub("", line)
    line = line.replace("\x7f", "•")  # viñeta sin mapeo Unicode, común en PDFs generados
    return " ".join(line.split())


def _iter_paragraphs(input_path: str):
    """
    Recorre el PDF con pypdf, línea por línea, y agrupa líneas en párrafos
    usando una heurística de puntuación: una línea que termina en punto,
    signo de exclamación/interrogación, o dos puntos, se asume que cierra
    un párrafo; el resto se van uniendo (para reconstruir párrafos que el
    PDF partió en varias líneas visuales).
    """
    from pypdf import PdfReader

    reader = PdfReader(input_path)

    for page in reader.pages:
        raw_text = page.extract_text() or ""
        current = []

        for raw_line in raw_text.split("\n"):
            line = _clean_line(raw_line)
            if not line:
                if current:
                    yield " ".join(current)
                    current = []
                continue

            current.append(line)

            if line.endswith(_SENTENCE_END) or line.startswith("•"):
                yield " ".join(current)
                current = []

        if current:
            yield " ".join(current)

        yield None  # marcador de fin de página (salto de página en el docx)


def convert_pdf_to_word(
    input_path: str,
    output_path: str,
    progress_cb: ProgressCallback = None,
) -> None:
    """Convierte un PDF (con texto seleccionable) a un .docx usando un motor Python puro."""
    if not has_selectable_text(input_path):
        raise ConversionError(
            "Este PDF parece ser un documento escaneado (sin texto seleccionable). "
            "La versión para Android de DocConvert NCTS no incluye OCR; "
            "usa la versión de escritorio para este archivo."
        )

    if progress_cb:
        progress_cb("Extrayendo texto del PDF...")

    paragraphs = []

    try:
        for item in _iter_paragraphs(input_path):
            if item is None:
                continue
            paragraphs.append(item)
    except Exception as exc:
        raise ConversionError(f"Error al leer el PDF: {exc}")

    if not paragraphs:
        raise ConversionError("No se pudo extraer texto del PDF (puede estar dañado o vacío).")

    if progress_cb:
        progress_cb("Guardando documento Word...")

    try:
        docx_lite.write_docx(paragraphs, output_path)
    except Exception as exc:
        raise ConversionError(f"Error al guardar el documento Word: {exc}")

    if not os.path.isfile(output_path):
        raise ConversionError("La conversión finalizó pero no se generó el archivo Word.")
