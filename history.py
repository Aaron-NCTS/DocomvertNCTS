"""
"Mis archivos creados" - historial local de conversiones para DocConvert NCTS.

Se guarda como un archivo JSON simple dentro del almacenamiento privado de
la app (o en el home del usuario, en escritorio). No se sube a ningún lado.

IMPORTANTE: esta sección es solo para archivos que SÍ se crearon
correctamente. Las conversiones fallidas se avisan con un popup de error
en el momento, pero NUNCA se guardan aquí -- por eso `add_entry()` valida
que el archivo exista y tenga contenido antes de agregarlo, y `load_history()`
vuelve a validar cada vez que se carga, descartando en silencio cualquier
registro cuyo archivo ya no sea válido (se borró, se movió, quedó vacío,
o es ilegible). No se muestran registros "No disponible": si no es válido,
simplemente se quita de la lista.
"""

import json
import os
import time
import uuid

try:
    from android.storage import app_storage_path
    ON_ANDROID = True
except Exception:
    ON_ANDROID = False

MAX_ENTRIES = 50


def _history_file_path() -> str:
    if ON_ANDROID:
        try:
            base = app_storage_path()
        except Exception:
            base = "/data/local/tmp"
    else:
        base = os.path.expanduser("~")
    return os.path.join(base, "docconvert_history.json")


def _is_entry_valid(entry: dict) -> bool:
    """
    Comprueba que un registro del historial siga siendo válido: tiene una
    ruta real, el archivo existe, no está vacío, y se puede abrir para
    lectura. Si algo de esto falla, el registro se descarta silenciosamente
    (no se muestra con un estado "No disponible" -- se elimina).
    """
    path = entry.get("path", "")
    if not path:
        return False
    if not os.path.isfile(path):
        return False
    try:
        if os.path.getsize(path) <= 0:
            return False
    except OSError:
        return False
    try:
        with open(path, "rb") as f:
            f.read(1)
    except OSError:
        return False
    return True


def load_history() -> list:
    """Carga el historial, descartando (y guardando ya limpio) cualquier registro inválido."""
    path = _history_file_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    valid_entries = [e for e in data if isinstance(e, dict) and _is_entry_valid(e)]

    if len(valid_entries) != len(data):
        _save_history(valid_entries)

    return valid_entries


def _save_history(history: list) -> None:
    try:
        with open(_history_file_path(), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_entry(
    name: str,
    mode_label: str,
    status: str,
    path: str = "",
    size_bytes=None,
    mime_type: str = "",
    content_uri: str = "",
) -> list:
    """
    Agrega una entrada al historial y devuelve la lista actualizada (más
    reciente primero). Solo se agrega si el archivo realmente existe, no
    está vacío, y se puede abrir para lectura -- "Mis archivos creados" es
    exclusivamente para resultados válidos, nunca para intentos fallidos.
    """
    if status == "Completado":
        if not path or not os.path.isfile(path):
            return load_history()
        try:
            if os.path.getsize(path) <= 0:
                return load_history()
            with open(path, "rb") as f:
                f.read(1)
        except OSError:
            return load_history()

    history = load_history()
    ext = os.path.splitext(name)[1].lstrip(".").upper() if name else ""

    entry = {
        "id": uuid.uuid4().hex,
        "name": name,
        "ext": ext,
        "mode": mode_label,
        "status": status,
        "path": path,
        "content_uri": content_uri,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "timestamp": time.strftime("%d/%m/%Y %H:%M"),
        "timestamp_epoch": time.time(),
    }
    history.insert(0, entry)
    history = history[:MAX_ENTRIES]
    _save_history(history)
    return history


def update_entry(entry_id: str, **fields) -> list:
    """Actualiza campos de una entrada existente (ej. tras renombrar un archivo)."""
    history = load_history()
    for entry in history:
        if entry.get("id") == entry_id:
            entry.update(fields)
            break
    _save_history(history)
    return history


def remove_entry(entry_id: str) -> list:
    """Quita una entrada del historial (no borra el archivo -- eso lo hace quien llama)."""
    history = load_history()
    history = [e for e in history if e.get("id") != entry_id]
    _save_history(history)
    return history


def clear_history() -> None:
    try:
        path = _history_file_path()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
