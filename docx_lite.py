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

import os
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Firma binaria de los archivos .doc antiguos (OLE Compound File Binary
# Format) -- así se detecta un DOC real sin depender solo de la extensión.
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class DocxError(Exception):
    """Error específico al leer un .docx, con un mensaje ya listo para el usuario."""


def detect_legacy_doc(path: str) -> bool:
    """Detecta si un archivo es un .doc binario antiguo (no .docx), leyendo su firma real."""
    try:
        with open(path, "rb") as f:
            header = f.read(8)
        return header == _OLE_MAGIC
    except Exception:
        return False


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
# Protección básica contra "ZIP bombs": un DOCX normal jamás debería
# descomprimirse a más de esto. Un archivo que declare mucho más contenido
# del que es razonable para un documento de texto se rechaza antes de
# extraer nada.
_MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB
_MAX_DOCX_ZIP_ENTRIES = 5000


def validate_docx_quick(path: str) -> bytes:
    """
    Valida que un archivo sea un DOCX real y utilizable, sin parsear todo
    su contenido (rápido, pensado para usarse justo al seleccionar el
    archivo, antes de mostrarlo como "listo para convertir"). Regresa los
    bytes de word/document.xml si todo está bien.

    Lanza DocxError con un mensaje específico cuando:
    - El archivo no existe, está vacío, o no se puede leer.
    - Es en realidad un .doc antiguo (formato OLE binario).
    - No es un ZIP válido (dañado, o no es un documento en absoluto).
    - Es un ZIP válido pero no tiene la estructura interna de un DOCX real.
    - El ZIP declara un tamaño descomprimido irrazonable ("zip bomb").
    """
    if not os.path.isfile(path):
        raise DocxError("El archivo no existe o no se pudo leer.")

    if os.path.getsize(path) == 0:
        raise DocxError("El archivo está vacío.")

    if detect_legacy_doc(path):
        raise DocxError(
            "El formato DOC antiguo todavía no es compatible. Utiliza un archivo DOCX."
        )

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise DocxError(
            "El archivo seleccionado no pudo leerse como un documento DOCX. "
            "Selecciona otro archivo e inténtalo nuevamente."
        )
    except Exception as exc:
        raise DocxError(f"No se pudo abrir el documento: {exc}")

    with zf:
        infos = zf.infolist()
        if len(infos) > _MAX_DOCX_ZIP_ENTRIES:
            raise DocxError("El documento tiene una estructura interna inválida o sospechosa.")
        total_uncompressed = sum(i.file_size for i in infos)
        if total_uncompressed > _MAX_DOCX_UNCOMPRESSED_BYTES:
            raise DocxError("El documento tiene un contenido interno demasiado grande para procesarlo.")

        names = zf.namelist()
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise DocxError(
                "El archivo seleccionado no pudo leerse como un documento DOCX "
                "(le falta contenido interno esperado). Selecciona otro archivo "
                "e inténtalo nuevamente."
            )
        try:
            return zf.read("word/document.xml")
        except Exception as exc:
            raise DocxError(f"No se pudo leer el contenido del documento: {exc}")


def read_docx(path: str) -> List:
    """
    Lee un .docx y regresa una lista de objetos Paragraph y Table, en el
    orden en que aparecen en el documento.

    Lanza DocxError con un mensaje específico y entendible -- ver
    validate_docx_quick() para el detalle de cada caso.
    """
    xml_bytes = validate_docx_quick(path)

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DocxError(f"El documento DOCX tiene contenido XML dañado: {exc}")

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
