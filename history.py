"""
Historial local de conversiones para DocConvert NCTS.

Se guarda como un archivo JSON simple dentro del almacenamiento privado de
la app (o en el home del usuario, en escritorio). No se sube a ningún lado;
es solo para mostrar "Conversiones recientes" en la pantalla principal.
"""

import json
import os
import time

try:
    from android.storage import app_storage_path
    ON_ANDROID = True
except Exception:
    ON_ANDROID = False

MAX_ENTRIES = 20


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
    path = _history_file_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def add_entry(name: str, mode_label: str, status: str) -> list:
    """Agrega una entrada al historial y devuelve la lista actualizada (más reciente primero)."""
    history = load_history()
    entry = {
        "name": name,
        "mode": mode_label,
        "status": status,
        "timestamp": time.strftime("%d/%m/%Y %H:%M"),
    }
    history.insert(0, entry)
    history = history[:MAX_ENTRIES]

    try:
        with open(_history_file_path(), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return history


def clear_history() -> None:
    try:
        path = _history_file_path()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
