"""
Conversión Word -> PDF para la versión móvil (Android) de DocConvert NCTS.

Motor: python-docx (lectura) + fpdf2 (escritura del PDF). Ambos se
distribuyen como wheel universal (py3-none-any) y NINGUNO tiene una "receta"
de compilación en python-for-android que intente compilar extensiones en C
-- eso es justo lo que rompía a `reportlab` (su receta en p4a descarga una
versión antigua con un acelerador en C que no compila contra el NDK/Python
modernos). fpdf2 evita ese problema por completo.

Trade-off que debes conocer (igual que en el prototipo de escritorio):
- No reproduce imágenes, encabezados/pies de página, columnas múltiples,
  ni estilos de tabla avanzados del documento original.
- Tipografía y espaciados no son idénticos a los que generaría Word o
  LibreOffice (la versión de escritorio de DocConvert NCTS).
- Sí conserva: títulos (Heading 1/2/3), negritas/cursivas, tablas simples,
  y listas con viñetas.
"""

import os
from typing import Callable, Optional

ProgressCallback = Optional[Callable[[str], None]]

# Reemplazos comunes para caracteres que la fuente básica (Helvetica, solo
# latin-1) no soporta. Cualquier otro carácter fuera de rango se sustituye
# por "?" como último recurso, en vez de romper toda la conversión.
_CHAR_REPLACEMENTS = {
    "\u2192": "->",  # →
    "\u2190": "<-",  # ←
    "\u2013": "-",   # –
    "\u2014": "--",  # —
    "\u2018": "'",   # '
    "\u2019": "'",   # '
    "\u201c": '"',   # "
    "\u201d": '"',   # "
    "\u2022": "-",   # •
    "\u2026": "...", # …
}


def _sanitize_text(text: str) -> str:
    for original, replacement in _CHAR_REPLACEMENTS.items():
        text = text.replace(original, replacement)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


class ConversionError(Exception):
    pass


def convert_word_to_pdf(
    input_path: str,
    output_path: str,
    progress_cb: ProgressCallback = None,
) -> None:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        from fpdf import FPDF
    except ImportError as exc:
        raise ConversionError(f"Faltan librerías necesarias: {exc}")

    if progress_cb:
        progress_cb("Leyendo documento Word...")

    try:
        doc = Document(input_path)
    except Exception as exc:
        raise ConversionError(f"No se pudo abrir el documento Word: {exc}")

    if progress_cb:
        progress_cb("Generando PDF...")

    pdf = FPDF(format="letter")
    pdf.set_margins(22, 22, 22)
    pdf.set_auto_page_break(True, margin=22)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10.5)

    HEADING_SIZES = {"Heading 1": 18, "Heading 2": 14, "Heading 3": 12}

    def write_paragraph(paragraph) -> None:
        text = _sanitize_text(paragraph.text.strip())
        if not text:
            pdf.ln(4)
            return

        style_name = paragraph.style.name if paragraph.style else "Normal"

        if style_name in HEADING_SIZES:
            pdf.set_font("Helvetica", style="B", size=HEADING_SIZES[style_name])
            pdf.multi_cell(0, HEADING_SIZES[style_name] * 0.6 + 2, text)
            pdf.set_font("Helvetica", size=10.5)
            pdf.ln(2)
            return

        if style_name == "List Bullet":
            pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(0, 6, f"-  {text}")
            return

        any_run = False
        for run in paragraph.runs:
            if not run.text:
                continue
            any_run = True
            style = ""
            if run.bold:
                style += "B"
            if run.italic:
                style += "I"
            pdf.set_font("Helvetica", style=style, size=10.5)
            pdf.write(6, _sanitize_text(run.text))
        if not any_run:
            pdf.set_font("Helvetica", size=10.5)
            pdf.write(6, text)
        pdf.ln(8)
        pdf.set_font("Helvetica", size=10.5)

    def write_table(table) -> None:
        rows = [[_sanitize_text(cell.text) for cell in row.cells] for row in table.rows]
        if not rows:
            return
        col_count = max(len(r) for r in rows)
        usable_width = pdf.w - pdf.l_margin - pdf.r_margin
        col_width = usable_width / col_count

        pdf.ln(2)
        for r_index, row in enumerate(rows):
            is_header = r_index == 0
            pdf.set_font("Helvetica", style="B" if is_header else "", size=9)
            if is_header:
                pdf.set_fill_color(44, 62, 80)
                pdf.set_text_color(255, 255, 255)
            else:
                if r_index % 2 == 0:
                    pdf.set_fill_color(245, 245, 245)
                else:
                    pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(0, 0, 0)

            row_x = pdf.l_margin
            row_y = pdf.get_y()
            max_h = 8
            for cell_text in row:
                pdf.set_xy(row_x, row_y)
                pdf.multi_cell(col_width, max_h, cell_text, border=1, fill=True)
                row_x += col_width
            pdf.set_y(row_y + max_h)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=10.5)
        pdf.ln(4)

    try:
        wrote_anything = False
        for block in doc.element.body:
            if block.tag.endswith("}p"):
                paragraph = Paragraph(block, doc)
                write_paragraph(paragraph)
                if paragraph.text.strip():
                    wrote_anything = True
            elif block.tag.endswith("}tbl"):
                table = Table(block, doc)
                write_table(table)
                wrote_anything = True

        if not wrote_anything:
            raise ConversionError("El documento Word está vacío o no se pudo leer su contenido.")

        pdf.output(output_path)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Error al generar el PDF: {exc}")

    if not os.path.isfile(output_path):
        raise ConversionError("La conversión finalizó pero no se generó el archivo PDF.")
