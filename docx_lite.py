"""
Lector/escritor mínimo de archivos Word (.docx) usando ÚNICAMENTE la
librería estándar de Python (zipfile + xml.etree.ElementTree).

Por qué existe este módulo: python-docx depende de lxml, que en repetidas
pruebas resultó imposible de compilar de forma confiable para Android
(python-for-android trae una receta de lxml vieja incompatible con Python
3.11+, y las versiones más nuevas de lxml requieren auto-compilar
libiconv/libxml2/libxslt de formas que no funcionan en este entorno de
compilación cruzada). Un archivo .docx es, en el fondo, solo un ZIP con
XML adentro (formato OOXML) -- no hace falta ninguna librería externa
para leerlo o escribirlo en los casos simples que necesita esta app.

Alcance (suficiente para DocConvert NCTS):
- Lectura: párrafos (con estilo Heading 1/2/3, negritas/cursivas por
  "run") y tablas simples (filas/celdas de texto).
- Escritura: párrafos de texto plano, uno por línea.

NO soporta: imágenes, encabezados/pies de página, listas numeradas
automáticas, estilos de párrafo avanzados, ni edición de un .docx
existente conservando su formato -- para esta app no se necesita.
"""

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Paragraph:
    runs: List[Run] = field(default_factory=list)
    style: Optional[str] = None

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class Table:
    rows: List[List[str]] = field(default_factory=list)


# --------------------------------------------------------------- Lectura
def read_docx(path: str) -> List:
    """
    Lee un .docx y regresa una lista de objetos Paragraph y Table, en el
    orden en que aparecen en el documento.
    """
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    body = root.find(_w("body"))
    if body is None:
        return []

    items = []
    for child in body:
        if child.tag == _w("p"):
            items.append(_parse_paragraph(child))
        elif child.tag == _w("tbl"):
            items.append(_parse_table(child))
    return items


def _parse_paragraph(p_elem) -> Paragraph:
    style = None
    p_pr = p_elem.find(_w("pPr"))
    if p_pr is not None:
        p_style = p_pr.find(_w("pStyle"))
        if p_style is not None:
            style = p_style.get(_w("val"))

    runs = []
    for r_elem in p_elem.findall(_w("r")):
        text_parts = [t.text or "" for t in r_elem.findall(_w("t"))]
        text = "".join(text_parts)
        if not text:
            # <w:tab/> y <w:br/> no tienen texto propio; los tratamos
            # como espacio/salto para no perder separación entre runs.
            if r_elem.find(_w("tab")) is not None:
                text = "\t"
            elif r_elem.find(_w("br")) is not None:
                text = "\n"
        r_pr = r_elem.find(_w("rPr"))
        bold = r_pr is not None and r_pr.find(_w("b")) is not None
        italic = r_pr is not None and r_pr.find(_w("i")) is not None
        runs.append(Run(text=text, bold=bold, italic=italic))

    return Paragraph(runs=runs, style=_style_name_from_id(style))


def _style_name_from_id(style_id: Optional[str]) -> Optional[str]:
    """
    Traduce el id interno de estilo (ej. 'Heading1') al nombre que ya
    usa el resto del código (ej. 'Heading 1'). Word suele usar IDs sin
    espacio para los estilos de título.
    """
    if not style_id:
        return None
    mapping = {
        "Heading1": "Heading 1",
        "Heading2": "Heading 2",
        "Heading3": "Heading 3",
        "ListBullet": "List Bullet",
    }
    return mapping.get(style_id, style_id)


def _parse_table(tbl_elem) -> Table:
    rows = []
    for tr in tbl_elem.findall(_w("tr")):
        cells = []
        for tc in tr.findall(_w("tc")):
            texts = []
            for t in tc.iter(_w("t")):
                texts.append(t.text or "")
            cells.append("".join(texts))
        rows.append(cells)
    return Table(rows=rows)


# -------------------------------------------------------------- Escritura
_DOCUMENT_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{ns}">
<w:body>
{paragraphs}
<w:sectPr/>
</w:body>
</w:document>"""

_CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def write_docx(paragraph_texts: List[str], output_path: str) -> None:
    """Escribe un .docx simple: un párrafo de texto plano por cada string de la lista."""
    paragraphs_xml = []
    for text in paragraph_texts:
        safe_text = _escape_xml(text)
        paragraphs_xml.append(
            f'<w:p><w:r><w:t xml:space="preserve">{safe_text}</w:t></w:r></w:p>'
        )

    document_xml = _DOCUMENT_XML_TEMPLATE.format(
        ns=W_NS, paragraphs="\n".join(paragraphs_xml)
    )

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", _RELS_XML)
        zf.writestr("word/document.xml", document_xml)
