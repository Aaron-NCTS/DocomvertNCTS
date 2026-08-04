"""
"Mis archivos creados" - historial local de conversiones para DocConvert NCTS.

Se guarda como un archivo JSON simple dentro del almacenamiento privado de
la app (o en el home del usuario, en escritorio). No se sube a ningún lado.

Cada entrada guarda metadatos completos (no solo nombre/estado) para poder
mostrar tamaño, tipo de conversión, fecha, y para que Abrir/Compartir/
Renombrar/Eliminar operen sobre la ruta real del archivo.
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


def load_history() -> list:
    """
    Carga el historial y, de paso, marca como 'Archivo no disponible' cualquier
    entrada cuyo archivo ya no exista físicamente (se movió o se borró desde
    fuera de la app) -- nunca se elimina la entrada sola por eso, para que el
    usuario vea qué pasó en vez de que desaparezca sin explicación.
    """
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

    changed = False
    for entry in data:
        real_path = entry.get("path", "")
        if entry.get("status") == "Completado" and real_path and not os.path.isfile(real_path):
            entry["status"] = "No disponible"
            changed = True

    if changed:
        _save_history(data)

    return data


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
) -> list:
    """Agrega una entrada al historial y devuelve la lista actualizada (más reciente primero)."""
    history = load_history()
    ext = os.path.splitext(name)[1].lstrip(".").upper() if name else ""

    entry = {
        "id": uuid.uuid4().hex,
        "name": name,
        "ext": ext,
        "mode": mode_label,
        "status": status,
        "path": path,
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
