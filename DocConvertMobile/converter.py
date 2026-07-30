"""
Conversión PDF -> Word para la versión móvil (Android) de DocConvert NCTS.

Motor: pdf2docx (Python puro sobre PyMuPDF). Misma lógica que la versión
de escritorio para PDFs con texto seleccionable.

La ruta OCR (PDFs escaneados) queda fuera del alcance de esta versión móvil:
tesseract no está disponible de forma confiable en Android sin un binario
nativo empaquetado aparte. Si el PDF no tiene texto extraíble, se informa
al usuario en lugar de fallar en silencio.
"""

import os
from typing import Callable, Optional

ProgressCallback = Optional[Callable[[str], None]]


class ConversionError(Exception):
    pass


def has_selectable_text(input_path: str, sample_pages: int = 3) -> bool:
    """Heurística rápida: revisa si las primeras páginas tienen texto extraíble."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(input_path)
        pages_to_check = min(sample_pages, len(doc))
        for i in range(pages_to_check):
            text = doc[i].get_text().strip()
            if len(text) > 20:
                doc.close()
                return True
        doc.close()
        return False
    except Exception:
        return True  # asumir que sí tiene texto y dejar que pdf2docx lo intente


def convert_pdf_to_word(
    input_path: str,
    output_path: str,
    progress_cb: ProgressCallback = None,
) -> None:
    """Convierte un PDF (con texto seleccionable) a un .docx."""
    if not has_selectable_text(input_path):
        raise ConversionError(
            "Este PDF parece ser un documento escaneado (sin texto seleccionable). "
            "La versión para Android de DocConvert NCTS no incluye OCR; "
            "usa la versión de escritorio para este archivo."
        )

    try:
        from pdf2docx import Converter
    except ImportError as exc:
        raise ConversionError(f"La librería pdf2docx no está disponible: {exc}")

    if progress_cb:
        progress_cb("Analizando estructura del PDF...")

    cv = None
    try:
        cv = Converter(input_path)
        cv.convert(output_path, start=0, end=None)
    except Exception as exc:
        raise ConversionError(f"Error al convertir el PDF: {exc}")
    finally:
        if cv is not None:
            try:
                cv.close()
            except Exception:
                pass

    if not os.path.isfile(output_path):
        raise ConversionError("La conversión finalizó pero no se generó el archivo Word.")
