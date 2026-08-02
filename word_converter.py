"""
Conversión Word -> PDF para la versión móvil (Android) de DocConvert NCTS.

Motor: python-docx (lectura) + reportlab (escritura del PDF). Ambos se
distribuyen como wheel universal (py3-none-any), es decir, son 100% Python
puro y no necesitan compilarse para Android.

Trade-off que debes conocer (igual que en el prototipo de escritorio):
- No reproduce imágenes, encabezados/pies de página, columnas múltiples,
  ni estilos de tabla avanzados del documento original.
- Tipografía y espaciados no son idénticos a los que generaría Word o
  LibreOffice (la versión de escritorio de DocConvert NCTS).
- Sí conserva: títulos (Heading 1/2/3), negritas/cursivas/subrayado,
  tablas simples, y listas con viñetas.
"""

import os
from typing import Callable, Optional

ProgressCallback = Optional[Callable[[str], None]]


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
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph as RLParagraph,
            Spacer,
            Table as RLTable,
            TableStyle,
        )
    except ImportError as exc:
        raise ConversionError(f"Faltan librerías necesarias: {exc}")

    if progress_cb:
        progress_cb("Leyendo documento Word...")

    styles = getSampleStyleSheet()
    heading_styles = {
        "Heading 1": ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, spaceAfter=12),
        "Heading 2": ParagraphStyle("H2", parent=styles["Heading2"], fontSize=14, spaceAfter=10),
        "Heading 3": ParagraphStyle("H3", parent=styles["Heading3"], fontSize=12, spaceAfter=8),
    }
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10.5, spaceAfter=6, leading=14)
    bullet_style = ParagraphStyle("Bullet", parent=body_style, leftIndent=18, bulletIndent=6, spaceAfter=4)

    def runs_to_html(paragraph) -> str:
        parts = []
        for run in paragraph.runs:
            text = run.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if not text:
                continue
            if run.bold:
                text = f"<b>{text}</b>"
            if run.italic:
                text = f"<i>{text}</i>"
            if run.underline:
                text = f"<u>{text}</u>"
            parts.append(text)
        return "".join(parts) if parts else paragraph.text

    def convert_table(table) -> "RLTable | None":
        data = [[cell.text for cell in row.cells] for row in table.rows]
        if not data:
            return None
        rl_table = RLTable(data, hAlign="LEFT")
        rl_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return rl_table

    try:
        doc = Document(input_path)
    except Exception as exc:
        raise ConversionError(f"No se pudo abrir el documento Word: {exc}")

    if progress_cb:
        progress_cb("Generando PDF...")

    flow = []
    try:
        for block in doc.element.body:
            if block.tag.endswith("}p"):
                paragraph = Paragraph(block, doc)
                text = paragraph.text.strip()
                if not text:
                    flow.append(Spacer(1, 6))
                    continue

                style_name = paragraph.style.name if paragraph.style else "Normal"
                html = runs_to_html(paragraph)

                if style_name in heading_styles:
                    flow.append(RLParagraph(html, heading_styles[style_name]))
                elif style_name == "List Bullet":
                    flow.append(RLParagraph(f"&bull;&nbsp;&nbsp;{html}", bullet_style))
                else:
                    flow.append(RLParagraph(html, body_style))

            elif block.tag.endswith("}tbl"):
                table = Table(block, doc)
                rl_table = convert_table(table)
                if rl_table:
                    flow.append(Spacer(1, 6))
                    flow.append(rl_table)
                    flow.append(Spacer(1, 10))

        if not flow:
            raise ConversionError("El documento Word está vacío o no se pudo leer su contenido.")

        pdf = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            topMargin=0.9 * inch,
            bottomMargin=0.9 * inch,
            leftMargin=0.9 * inch,
            rightMargin=0.9 * inch,
        )
        pdf.build(flow)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Error al generar el PDF: {exc}")

    if not os.path.isfile(output_path):
        raise ConversionError("La conversión finalizó pero no se generó el archivo PDF.")
