"""
Utilidades específicas de Android: permisos de almacenamiento y carpeta de salida.

Todo lo relacionado con `android.permissions` y `jnius` se importa de forma
perezosa y protegida, para que este mismo código corra sin romperse en
escritorio (útil mientras se prueba la app con `python main.py` antes de
compilar el APK).
"""

import os
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
