"""
Selector de archivos nativo de Android (Storage Access Framework), usando
pyjnius directamente en vez de plyer.filechooser.

Por qué se reemplazó plyer.filechooser: revisando su código fuente
(plyer/platforms/android/filechooser.py), su parámetro `filters` solo
acepta como PRIMER elemento una palabra clave string de un diccionario
fijo ("pdf", "docx", "image", etc.) -- si no es exactamente ese formato
(nosotros pasábamos tuplas como `("Documentos PDF", "*.pdf")`), plyer
calla el error y hace `setType("*/*")`, es decir, sin filtro real. Eso
es justo lo que se ve en el video: el selector de Android abre en modo
"Recientes" mostrando imágenes/videos porque no hay ningún filtro MIME
real aplicado. Además, el diccionario de plyer no soporta múltiples
MIME types a la vez (por ejemplo, para Word necesitamos aceptar tanto
.doc como .docx), lo cual tampoco era posible con su API.

Esta implementación usa directamente:
- Intent.ACTION_OPEN_DOCUMENT (el selector moderno de Android, con acceso
  correcto vía Storage Access Framework).
- Intent.EXTRA_MIME_TYPES para aceptar varios tipos MIME a la vez.
- Intent.EXTRA_ALLOW_MULTIPLE para selección múltiple.
- Intent.getClipData() para varios archivos, con getData() como respaldo
  para selección única.
- takePersistableUriPermission() para poder seguir leyendo el archivo
  más adelante (no solo en el momento de la selección).
- android.activity.bind(on_activity_result=...) para recibir el resultado,
  igual que hace plyer internamente -- pero con nuestro propio manejo del
  request_code, mime types y selección múltiple, todo correcto.
"""

import os
import uuid
from typing import Callable, List, Optional

try:
    from android import activity, mActivity
    from jnius import autoclass, cast

    ON_ANDROID = True
except Exception:
    ON_ANDROID = False

# Un request_code fijo por tipo de selección, para poder distinguir
# cuál Intent.ACTION_OPEN_DOCUMENT respondió cuando Android regresa a la app.
REQUEST_CODE_PDF = 91001
REQUEST_CODE_WORD = 91002
REQUEST_CODE_IMAGES = 91003

MIME_TYPES = {
    "pdf": ["application/pdf"],
    "word": [
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    "images": [
        "image/jpeg",
        "image/png",
        "image/webp",
    ],
}

_REQUEST_CODES_BY_KIND = {
    "pdf": REQUEST_CODE_PDF,
    "word": REQUEST_CODE_WORD,
    "images": REQUEST_CODE_IMAGES,
}

# callbacks activos por request_code (se registran al abrir el selector,
# se limpian después de usarse).
_pending_callbacks = {}
_listener_bound = False


def _log(msg: str) -> None:
    """Registro de depuración (solo va a la consola/logcat, nunca a la UI)."""
    try:
        print(f"[DocConvertNCTS filechooser] {msg}")
    except Exception:
        pass


def _ensure_listener_bound() -> None:
    global _listener_bound
    if not ON_ANDROID or _listener_bound:
        return
    activity.bind(on_activity_result=_on_activity_result)
    _listener_bound = True


def open_document(kind: str, multiple: bool, on_selection: Callable[[List[str]], None]) -> bool:
    """
    Abre el selector de documentos de Android para `kind` ("pdf", "word" o
    "images"), con selección múltiple opcional. `on_selection` se llama
    (en el hilo principal) con la lista de URIs content:// seleccionadas,
    o una lista vacía si el usuario canceló.

    Regresa False de inmediato si no estamos en Android (para que quien
    llama pueda usar un selector alterno en escritorio).
    """
    if not ON_ANDROID:
        return False

    if kind not in MIME_TYPES:
        _log(f"kind desconocido: {kind}")
        on_selection([])
        return True

    _ensure_listener_bound()

    try:
        Intent = autoclass("android.content.Intent")

        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")

        mime_types = MIME_TYPES[kind]
        StringClass = autoclass("java.lang.String")

        # pyjnius necesita un arreglo Java de String (String[]) para
        # EXTRA_MIME_TYPES; se construye vía java.lang.reflect.Array.
        JArray = autoclass("java.lang.reflect.Array")
        mime_java_array = JArray.newInstance(StringClass, len(mime_types))
        for index, mime in enumerate(mime_types):
            JArray.set(mime_java_array, index, StringClass(mime))

        intent.putExtra(Intent.EXTRA_MIME_TYPES, mime_java_array)

        if multiple:
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)

        request_code = _REQUEST_CODES_BY_KIND[kind]
        _pending_callbacks[request_code] = on_selection

        _log(f"Abriendo selector para kind={kind}, mime_types={mime_types}, "
             f"multiple={multiple}, request_code={request_code}")

        mActivity.startActivityForResult(intent, request_code)
        return True
    except Exception as exc:
        _log(f"Error al abrir el selector: {exc}")
        on_selection([])
        return True


def _on_activity_result(request_code, result_code, data):
    """Listener de android.app.Activity.onActivityResult()."""
    callback = _pending_callbacks.pop(request_code, None)
    if callback is None:
        return  # no era nuestra solicitud

    _log(f"on_activity_result: request_code={request_code}, result_code={result_code}")

    try:
        Activity = autoclass("android.app.Activity")
        if result_code != Activity.RESULT_OK or data is None:
            _log("Selección cancelada por el usuario.")
            _schedule_callback(callback, [])
            return

        uris = []
        clip_data = data.getClipData()
        if clip_data is not None:
            for i in range(clip_data.getItemCount()):
                item_uri = clip_data.getItemAt(i).getUri()
                if item_uri is not None:
                    uris.append(item_uri)
        else:
            single_uri = data.getData()
            if single_uri is not None:
                uris.append(single_uri)

        _log(f"URIs recibidas: {len(uris)}")

        # Permiso persistente: para poder volver a leer el archivo más
        # adelante (ej. si el usuario minimiza la app durante la
        # conversión), no solo en este instante.
        Intent = autoclass("android.content.Intent")
        flags = Intent.FLAG_GRANT_READ_URI_PERMISSION
        resolver = mActivity.getContentResolver()
        for uri in uris:
            try:
                resolver.takePersistableUriPermission(uri, flags)
            except Exception as exc:
                _log(f"No se pudo tomar permiso persistente para {uri}: {exc}")

        uri_strings = [uri.toString() for uri in uris]
        _schedule_callback(callback, uri_strings)
    except Exception as exc:
        _log(f"Error procesando el resultado del selector: {exc}")
        _schedule_callback(callback, [])


def _schedule_callback(callback, result) -> None:
    """Llama al callback en el hilo principal de Kivy (Clock.schedule_once)."""
    from kivy.clock import Clock

    Clock.schedule_once(lambda dt: callback(result), 0)


def open_camera_capture(on_photo_taken: Callable[[Optional[str]], None], dest_dir: str) -> bool:
    """
    Abre la cámara del sistema (Intent.ACTION_IMAGE_CAPTURE) usando un
    content:// URI seguro vía FileProvider (no file:// expuesto). Guarda
    la foto en `dest_dir` y llama a `on_photo_taken(ruta_o_none)`.
    """
    if not ON_ANDROID:
        return False

    try:
        Intent = autoclass("android.content.Intent")
        JavaFile = autoclass("java.io.File")
        FileProvider = autoclass("androidx.core.content.FileProvider")

        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, f"foto_{uuid.uuid4().hex}.jpg")
        file_obj = JavaFile(dest_path)

        authority = mActivity.getPackageName() + ".fileprovider"
        photo_uri = FileProvider.getUriForFile(mActivity, authority, file_obj)

        intent = Intent(Intent.ACTION_IMAGE_CAPTURE)
        intent.putExtra("android.intent.extra.OUTPUT", photo_uri)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)

        request_code = 91004
        _ensure_listener_bound()

        def _after_capture(uri_list):
            # ACTION_IMAGE_CAPTURE no regresa datos en el Intent; el
            # resultado es simplemente que dest_path ya tiene la foto
            # (o no, si se canceló).
            if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
                on_photo_taken(dest_path)
            else:
                on_photo_taken(None)

        _pending_callbacks[request_code] = _after_capture
        mActivity.startActivityForResult(intent, request_code)
        return True
    except Exception as exc:
        _log(f"No se pudo abrir la cámara: {exc}")
        on_photo_taken(None)
        return True
