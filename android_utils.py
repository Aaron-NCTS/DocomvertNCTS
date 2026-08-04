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
    # READ_MEDIA_IMAGES es un permiso más nuevo (Android 13+); no todas las
    # versiones de python-for-android/plyer lo tienen definido en su enum
    # Permission, así que lo agregamos con manejo seguro.
    try:
        REQUIRED_PERMISSIONS.append(Permission.READ_MEDIA_IMAGES)
    except AttributeError:
        pass


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


def ensure_camera_permission(callback=None) -> None:
    """Solicita el permiso de cámara solo cuando el usuario intenta usarla."""
    if not ON_ANDROID:
        if callback:
            callback(True)
        return

    try:
        camera_perm = Permission.CAMERA
    except AttributeError:
        # Este runtime no define el permiso de cámara; no podemos pedirlo,
        # pero tampoco bloqueamos -- el intent de cámara del sistema puede
        # funcionar igual dependiendo del fabricante.
        if callback:
            callback(True)
        return

    if check_permission(camera_perm):
        if callback:
            callback(True)
        return

    def _on_result(permissions, grants):
        if callback:
            callback(all(grants))

    request_permissions([camera_perm], _on_result)


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


_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def sanitize_filename(name: str, fallback: str = "documento") -> str:
    """Quita caracteres no permitidos en nombres de archivo en Android/Windows."""
    name = (name or "").strip()
    cleaned = "".join(c for c in name if c not in _INVALID_FILENAME_CHARS).strip()
    cleaned = cleaned.rstrip(".")  # Windows no permite terminar en punto
    return cleaned or fallback


def resolve_unique_path(directory: str, filename: str) -> str:
    """
    Si ya existe un archivo con ese nombre en `directory`, agrega ' (1)',
    ' (2)', etc. hasta encontrar un nombre libre. Regresa la ruta completa.
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return os.path.join(directory, candidate)


def rename_file(old_path: str, new_name: str) -> str:
    """
    Renombra un archivo ya guardado, evitando colisiones con otro archivo
    existente. Regresa la nueva ruta completa. Lanza IOError si algo falla.
    """
    if not os.path.isfile(old_path):
        raise IOError("El archivo ya no existe; no se puede renombrar.")

    directory = os.path.dirname(old_path)
    _, old_ext = os.path.splitext(old_path)
    new_name = sanitize_filename(new_name)

    # Conservar la extensión original: el usuario renombra el "título",
    # no debería poder cambiar accidentalmente .pdf a otra cosa.
    new_base, new_ext = os.path.splitext(new_name)
    if not new_ext:
        new_name = new_base + old_ext

    new_path = resolve_unique_path(directory, new_name)
    if new_path == old_path:
        return old_path

    try:
        os.rename(old_path, new_path)
    except Exception as exc:
        raise IOError(f"No se pudo renombrar el archivo: {exc}")

    notify_media_scanner(new_path)
    return new_path


def delete_file(path: str) -> bool:
    """Elimina un archivo generado por la app. Regresa True si se borró (o ya no existía)."""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
        return True
    except Exception:
        return False


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


def _mime_for(file_path: str) -> str:
    if file_path.lower().endswith(".pdf"):
        return "application/pdf"
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _build_shareable_uri(context, file_path: str):
    """
    Devuelve (uri, grant_flag) usando FileProvider si está disponible (necesario
    en Android 7+ para compartir/abrir archivos entre apps), o un URI de
    archivo directo como respaldo (solo funciona de forma confiable en
    versiones viejas de Android).
    """
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    Uri = autoclass("android.net.Uri")
    JavaFile = autoclass("java.io.File")

    file_obj = JavaFile(file_path)
    try:
        FileProvider = autoclass("androidx.core.content.FileProvider")
        authority = context.getPackageName() + ".fileprovider"
        uri = FileProvider.getUriForFile(context, authority, file_obj)
        return uri, Intent.FLAG_GRANT_READ_URI_PERMISSION
    except Exception:
        return Uri.fromFile(file_obj), 0


def open_file_external(file_path: str) -> bool:
    """
    Intenta abrir el archivo convertido con la app asociada de Android (ej.
    un visor de Word/PDF).

    Devuelve True si se pudo lanzar el intent, False si no (en cuyo caso
    quien llama debe mostrar la ubicación del archivo como alternativa,
    ya que el archivo sí quedó guardado correctamente de cualquier forma).
    """
    if not ON_ANDROID:
        return False
    try:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        context = PythonActivity.mActivity

        uri, grant_flag = _build_shareable_uri(context, file_path)

        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(uri, _mime_for(file_path))
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | grant_flag)
        context.startActivity(intent)
        return True
    except Exception:
        return False


def share_file_external(file_path: str) -> bool:
    """Abre el selector de 'Compartir' de Android (WhatsApp, Gmail, Drive, etc.) con el archivo."""
    if not ON_ANDROID:
        return False
    try:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        context = PythonActivity.mActivity

        uri, grant_flag = _build_shareable_uri(context, file_path)

        intent = Intent(Intent.ACTION_SEND)
        intent.setType(_mime_for(file_path))
        intent.putExtra(Intent.EXTRA_STREAM, uri)
        intent.setFlags(grant_flag)
        chooser = Intent.createChooser(intent, "Compartir documento")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(chooser)
        return True
    except Exception:
        return False


def cleanup_temp_file(file_path: str, cache_dir: str) -> None:
    """
    Borra un archivo temporal creado por resolve_to_local_path (copia de un
    content:// URI), siempre y cuando esté dentro de la carpeta temporal de
    la app -- nunca borra archivos originales del usuario.
    """
    try:
        if file_path and os.path.isfile(file_path):
            if os.path.abspath(os.path.dirname(file_path)) == os.path.abspath(cache_dir):
                os.remove(file_path)
    except Exception:
        pass


# Antes este límite era de 25 MB. Se sube a 1 GB porque no hay razón técnica
# real para rechazar archivos más grandes -- ya copiamos y procesamos todo
# por streaming (bloques de 64 KB, nunca cargamos el archivo completo a
# memoria), así que el límite real pasa a ser "hay espacio en disco",
# no un número arbitrario.
MAX_FILE_SIZE_MB = 1024
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def get_free_disk_space(path: str) -> int:
    """Devuelve el espacio libre en bytes en la partición donde vive `path`."""
    try:
        stat = shutil.disk_usage(path if os.path.isdir(path) else os.path.dirname(path) or ".")
        return stat.free
    except Exception:
        return -1  # desconocido; quien llama debe decidir cómo tratarlo


def has_enough_space(directory: str, needed_bytes: int, safety_margin: float = 1.5) -> bool:
    """
    Comprueba que haya espacio suficiente para escribir un archivo de
    `needed_bytes`, con un margen de seguridad (por defecto 50% extra, para
    cubrir el archivo temporal ".part" y el resultado final coexistiendo).
    Si no se pudo determinar el espacio libre, se asume que sí hay
    (más vale intentar que bloquear sin motivo).
    """
    free = get_free_disk_space(directory)
    if free < 0:
        return True
    return free >= int(needed_bytes * safety_margin)


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
