"""
Utilidades específicas de Android: permisos de almacenamiento y carpeta de salida.

Todo lo relacionado con `android.permissions` y `jnius` se importa de forma
perezosa y protegida, para que este mismo código corra sin romperse en
escritorio (útil mientras se prueba la app con `python main.py` antes de
compilar el APK).
"""

import os
import shutil
import uuid
from pathlib import Path

try:
    from android.permissions import Permission, check_permission, request_permissions
    ON_ANDROID = True
except Exception:
    ON_ANDROID = False


REQUIRED_PERMISSIONS = []
if ON_ANDROID:
    REQUIRED_PERMISSIONS = [
        Permission.READ_EXTERNAL_STORAGE,
        Permission.WRITE_EXTERNAL_STORAGE,
    ]


def ensure_permissions(callback=None) -> None:
    """Solicita permisos de almacenamiento en Android. No-op en escritorio."""
    if not ON_ANDROID:
        if callback:
            callback(True)
        return

    all_granted = all(check_permission(p) for p in REQUIRED_PERMISSIONS)
    if all_granted:
        if callback:
            callback(True)
        return

    def _on_result(permissions, grants):
        if callback:
            callback(all(grants))

    request_permissions(REQUIRED_PERMISSIONS, _on_result)


def get_display_name(uri_str: str) -> str:
    """
    Obtiene el nombre real de un archivo desde un content:// URI, sin copiar
    su contenido (solo consulta metadatos). Si no es un content:// URI, o
    algo falla, regresa el último segmento de la ruta como respaldo.
    """
    if ON_ANDROID and uri_str.startswith("content://"):
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Uri = autoclass("android.net.Uri")

            context = PythonActivity.mActivity
            resolver = context.getContentResolver()
            uri = Uri.parse(uri_str)

            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None and cursor.moveToFirst():
                name_index = cursor.getColumnIndex("_display_name")
                if name_index != -1:
                    name = cursor.getString(name_index)
                    cursor.close()
                    if name:
                        return name
                cursor.close()
        except Exception:
            pass
        return "documento.pdf"

    return os.path.basename(uri_str) or "documento.pdf"


def resolve_to_local_path(path_or_uri: str, cache_dir: str) -> str:
    """
    En Android, el selector de archivos (plyer) puede devolver un URI tipo
    'content://...' en vez de una ruta de archivo normal (esto pasa cuando
    Android usa el Storage Access Framework). Python no puede abrir esas
    rutas directamente con open()/pypdf/python-docx, así que hay que copiar
    su contenido a un archivo real dentro del almacenamiento de la app.

    En escritorio (o si ya es una ruta de archivo normal), esta función
    simplemente regresa la misma ruta sin tocar nada.
    """
    if not (ON_ANDROID and path_or_uri.startswith("content://")):
        return path_or_uri

    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Uri = autoclass("android.net.Uri")

        context = PythonActivity.mActivity
        resolver = context.getContentResolver()
        uri = Uri.parse(path_or_uri)

        # Intentar recuperar el nombre real del archivo (si no, uno genérico).
        filename = get_display_name(path_or_uri) or f"{uuid.uuid4().hex}.pdf"

        os.makedirs(cache_dir, exist_ok=True)
        dest_path = os.path.join(cache_dir, filename)

        FileOutputStream = autoclass("java.io.FileOutputStream")
        input_stream = resolver.openInputStream(uri)
        output_stream = FileOutputStream(dest_path)
        try:
            buf = bytearray(64 * 1024)
            n = input_stream.read(buf)
            # Contrato de java.io.InputStream.read(): -1 = fin de archivo.
            # 0 NO significa EOF (puede pasar legítimamente); solo -1 lo es.
            while n != -1:
                if n > 0:
                    output_stream.write(buf, 0, n)
                n = input_stream.read(buf)
        finally:
            input_stream.close()
            output_stream.close()

        return dest_path
    except Exception as exc:
        raise IOError(f"No se pudo leer el archivo seleccionado ({exc})")


def get_file_size(path_or_uri: str):
    """Devuelve el tamaño en bytes del archivo/URI, o None si no se pudo determinar."""
    if ON_ANDROID and path_or_uri.startswith("content://"):
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Uri = autoclass("android.net.Uri")

            context = PythonActivity.mActivity
            resolver = context.getContentResolver()
            uri = Uri.parse(path_or_uri)

            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None and cursor.moveToFirst():
                size_index = cursor.getColumnIndex("_size")
                if size_index != -1:
                    size = cursor.getLong(size_index)
                    cursor.close()
                    return int(size)
                cursor.close()
        except Exception:
            pass
        return None

    try:
        return os.path.getsize(path_or_uri)
    except Exception:
        return None


def format_file_size(num_bytes) -> str:
    """Formatea un tamaño en bytes a texto legible (KB/MB/GB). Regresa '' si no se conoce."""
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def open_file_external(file_path: str) -> bool:
    """
    Intenta abrir el archivo convertido con la app asociada de Android (ej.
    un visor de Word/PDF), usando FileProvider para generar un content:// URI
    (requerido en Android 7+ para compartir archivos entre apps).

    Devuelve True si se pudo lanzar el intent, False si no (en cuyo caso
    quien llama debe mostrar la ubicación del archivo como alternativa,
    ya que el archivo sí quedó guardado correctamente de cualquier forma).
    """
    if not ON_ANDROID:
        return False
    try:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        JavaFile = autoclass("java.io.File")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")

        context = PythonActivity.mActivity
        file_obj = JavaFile(file_path)

        grant_flag = 0
        try:
            FileProvider = autoclass("androidx.core.content.FileProvider")
            authority = context.getPackageName() + ".fileprovider"
            uri = FileProvider.getUriForFile(context, authority, file_obj)
            grant_flag = Intent.FLAG_GRANT_READ_URI_PERMISSION
        except Exception:
            # Sin FileProvider configurado en el manifest: en Android <24
            # esto puede funcionar igual con un URI de archivo directo.
            uri = Uri.fromFile(file_obj)

        mime = (
            "application/pdf"
            if file_path.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(uri, mime)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | grant_flag)
        context.startActivity(intent)
        return True
    except Exception:
        return False


def temp_cache_dir() -> str:
    """Carpeta temporal privada de la app para copiar archivos content:// antes de procesarlos."""
    if ON_ANDROID:
        try:
            from android.storage import app_storage_path

            return os.path.join(app_storage_path(), "tmp_input")
        except Exception:
            return "/data/local/tmp/docconvertncts_tmp"
    else:
        import tempfile

        return os.path.join(tempfile.gettempdir(), "docconvertncts_tmp")


def default_output_dir() -> str:
    """Carpeta de salida: Download/DocConvert NCTS en Android, Documentos en escritorio."""
    if ON_ANDROID:
        try:
            from android.storage import primary_external_storage_path

            base = Path(primary_external_storage_path()) / "Download" / "DocConvert NCTS"
        except Exception:
            base = Path("/sdcard/Download/DocConvert NCTS")
    else:
        home = Path.home()
        docs = home / "Documents"
        base = (docs if docs.exists() else home) / "DocConvert NCTS"

    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def notify_media_scanner(file_path: str) -> None:
    """Hace visible el archivo recién creado en el explorador de archivos de Android."""
    if not ON_ANDROID:
        return
    try:
        from jnius import autoclass

        Context = autoclass("android.content.Context")
        MediaScannerConnection = autoclass("android.media.MediaScannerConnection")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        MediaScannerConnection.scanFile(
            PythonActivity.mActivity, [file_path], None, None
        )
    except Exception:
        pass
