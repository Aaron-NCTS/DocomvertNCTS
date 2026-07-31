"""
Conversión PDF -> Word para la versión móvil (Android) de DocConvert NCTS.

Motor: pdfminer.six + python-docx. Ambos son 100% Python puro (sin extensiones
en C), lo cual es indispensable en Android: pdf2docx/PyMuPDF (el motor de la
versión de escritorio) no se puede compilar para el entorno cruzado de
python-for-android, así que aquí usamos un motor distinto.

Trade-off que debes conocer: este motor extrae texto por párrafos y hace un
esfuerzo razonable por detectar saltos de línea/párrafo según posición
vertical, pero NO reconstruye tablas ni el layout visual exacto del PDF
original (eso sí lo hace pdf2docx en la versión de escritorio). Para PDFs de
texto corrido (cartas, reportes, contratos) el resultado es bueno. Para PDFs
con tablas o diseño complejo, el resultado pierde esa estructura.
"""

import os
import re
from typing import Callable, Optional

ProgressCallback = Optional[Callable[[str], None]]

_CID_PATTERN = re.compile(r"\(cid:\d+\)")


class ConversionError(Exception):
    pass


def has_selectable_text(input_path: str, sample_pages: int = 3) -> bool:
    """Heurística rápida: revisa si las primeras páginas tienen texto extraíble."""
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage

        with open(input_path, "rb") as f:
            page_count = 0
            for _ in PDFPage.get_pages(f):
                page_count += 1
                if page_count >= sample_pages:
                    break

        text = extract_text(input_path, page_numbers=list(range(min(sample_pages, page_count or 1))))
        return len(text.strip()) > 20
    except Exception:
        return True  # asumir que sí tiene texto y dejar que el motor lo intente


def _clean_text(text: str) -> str:
    """Limpia artefactos de glifos sin mapeo Unicode (típico en viñetas de PDFs generados)."""
    text = _CID_PATTERN.sub("", text)
    return " ".join(text.split())


def _iter_paragraphs(input_path: str):
    """
    Recorre el PDF con pdfminer. Cada "caja de texto" (LTTextContainer) que
    detecta pdfminer corresponde, en la gran mayoría de PDFs generados por
    procesadores de texto normales, a un párrafo o bloque de texto separado
    (título, párrafo, celda de tabla, etc.), así que se respeta esa
    agrupación en vez de reconstruirla manualmente línea por línea.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer

    for page_layout in extract_pages(input_path):
        containers = [
            el for el in page_layout if isinstance(el, LTTextContainer)
        ]
        containers.sort(key=lambda el: el.y0, reverse=True)

        for container in containers:
            text = _clean_text(container.get_text())
            if text:
                yield text

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

    try:
        from docx import Document
    except ImportError as exc:
        raise ConversionError(f"La librería python-docx no está disponible: {exc}")

    if progress_cb:
        progress_cb("Extrayendo texto del PDF...")

    doc = Document()
    wrote_anything = False

    try:
        for item in _iter_paragraphs(input_path):
            if item is None:
                continue
            doc.add_paragraph(item)
            wrote_anything = True
    except Exception as exc:
        raise ConversionError(f"Error al leer el PDF: {exc}")

    if not wrote_anything:
        raise ConversionError("No se pudo extraer texto del PDF (puede estar dañado o vacío).")

    if progress_cb:
        progress_cb("Guardando documento Word...")

    try:
        doc.save(output_path)
    except Exception as exc:
        raise ConversionError(f"Error al guardar el documento Word: {exc}")

    if not os.path.isfile(output_path):
        raise ConversionError("La conversión finalizó pero no se generó el archivo Word.")
