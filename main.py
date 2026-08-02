"""
DocConvert NCTS - Móvil
Convierte PDF <-> Word directamente en tu Android. 100% local, sin internet.
"""

import os
import threading
from pathlib import Path

from kivy.app import App
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

import history
from android_utils import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    cleanup_temp_file,
    default_output_dir,
    ensure_permissions,
    format_file_size,
    get_display_name,
    get_file_size,
    notify_media_scanner,
    open_file_external,
    resolve_to_local_path,
    share_file_external,
    temp_cache_dir,
)
from converter import ConversionError, convert_pdf_to_word
from word_converter import convert_word_to_pdf

# ------------------------------------------------------------------ Tema
BG = (0.06, 0.07, 0.10, 1)
CARD = (0.11, 0.12, 0.17, 1)
CARD_LIGHT = (0.15, 0.16, 0.22, 1)
HEADER = (0.05, 0.06, 0.09, 1)
ACCENT = (0.30, 0.50, 0.95, 1)
ACCENT_DIM = (0.20, 0.33, 0.62, 1)
SUCCESS = (0.20, 0.70, 0.45, 1)
ERROR = (0.90, 0.35, 0.38, 1)
WARNING = (0.90, 0.65, 0.25, 1)
TEXT_PRIMARY = (0.95, 0.95, 0.97, 1)
TEXT_SECONDARY = (0.68, 0.70, 0.78, 1)
TEXT_MUTED = (0.48, 0.50, 0.58, 1)

Window.clearcolor = BG

MODE_PDF_TO_WORD = "pdf_to_word"
MODE_WORD_TO_PDF = "word_to_pdf"

MODE_INFO = {
    MODE_PDF_TO_WORD: {
        "label": "PDF -> Word",
        "select_label": "Seleccionar PDF",
        "filters": [("Documentos PDF", "*.pdf")],
        "out_ext": ".docx",
        "empty_hint": "Aún no has agregado archivos PDF",
    },
    MODE_WORD_TO_PDF: {
        "label": "Word -> PDF",
        "select_label": "Seleccionar Word",
        "filters": [("Documentos Word", "*.docx")],
        "out_ext": ".pdf",
        "empty_hint": "Aún no has agregado archivos Word",
    },
}

KV = """
#:import dp kivy.metrics.dp

<SectionLabel@Label>:
    size_hint_y: None
    height: dp(26)
    font_size: "13sp"
    bold: True
    color: 0.68, 0.70, 0.78, 1
    halign: "left"
    valign: "middle"
    text_size: self.size

<FileRow>:
    orientation: "vertical"
    size_hint_y: None
    height: dp(148)
    padding: dp(14), dp(12)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: app.card_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

    BoxLayout:
        orientation: "horizontal"
        size_hint_y: None
        height: dp(20)
        spacing: dp(8)

        Label:
            text: root.file_name
            color: app.text_primary
            font_size: "14sp"
            bold: True
            halign: "left"
            valign: "middle"
            text_size: self.size
            shorten: True
            shorten_from: "right"

        Label:
            text: root.file_size
            color: app.text_muted
            size_hint_x: None
            width: dp(64)
            font_size: "11sp"
            halign: "right"
            valign: "middle"
            text_size: self.size

    Label:
        text: root.mode_label
        size_hint_y: None
        height: dp(16)
        font_size: "11sp"
        color: app.text_muted
        halign: "left"
        valign: "middle"
        text_size: self.size

    BoxLayout:
        orientation: "horizontal"
        size_hint_y: None
        height: dp(18)
        spacing: dp(6)

        Widget:
            size_hint_x: None
            width: dp(8)
            canvas:
                Color:
                    rgba: root.status_color
                Ellipse:
                    pos: self.x, self.y + dp(3)
                    size: dp(9), dp(9)

        Label:
            text: root.status_text
            color: root.status_color
            font_size: "12sp"
            halign: "left"
            valign: "middle"
            text_size: self.size

    ProgressBar:
        id: row_progress
        max: 1
        value: root.progress
        size_hint_y: None
        height: dp(6)

    BoxLayout:
        orientation: "horizontal"
        size_hint_y: None
        height: dp(34)
        spacing: dp(6)
        padding: 0, dp(4), 0, 0

        Button:
            text: "Abrir"
            font_size: "12sp"
            opacity: 1 if root.output_path else 0.35
            disabled: not root.output_path
            background_normal: ""
            background_color: 0.2, 0.55, 0.35, 1
            color: 1, 1, 1, 1
            on_release: root.on_open()

        Button:
            text: "Compartir"
            font_size: "12sp"
            opacity: 1 if root.output_path else 0.35
            disabled: not root.output_path
            background_normal: ""
            background_color: 0.22, 0.4, 0.75, 1
            color: 1, 1, 1, 1
            on_release: root.on_share()

        Button:
            text: "Eliminar"
            font_size: "12sp"
            size_hint_x: 0.7
            background_normal: ""
            background_color: 0.5, 0.18, 0.2, 1
            color: 1, 1, 1, 1
            on_release: root.on_remove(root.file_path)


<HistoryRow@BoxLayout>:
    name: ""
    mode: ""
    status: ""
    timestamp: ""
    orientation: "horizontal"
    size_hint_y: None
    height: dp(46)
    padding: dp(12), dp(6)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: app.card_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]

    BoxLayout:
        orientation: "vertical"
        Label:
            text: root.name
            color: app.text_primary
            font_size: "12sp"
            halign: "left"
            valign: "middle"
            text_size: self.size
            shorten: True
            shorten_from: "right"
        Label:
            text: root.mode + "  -  " + root.timestamp
            color: app.text_muted
            font_size: "10sp"
            halign: "left"
            valign: "middle"
            text_size: self.size

    Label:
        text: root.status
        size_hint_x: None
        width: dp(80)
        font_size: "11sp"
        color: (0.2, 0.7, 0.45, 1) if root.status == "Completado" else (0.85, 0.4, 0.4, 1)
        halign: "right"
        valign: "middle"
        text_size: self.size


BoxLayout:
    orientation: "vertical"
    canvas.before:
        Color:
            rgba: app.bg_color
        Rectangle:
            pos: self.pos
            size: self.size

    # --- Encabezado ---
    BoxLayout:
        orientation: "vertical"
        size_hint_y: None
        height: dp(78)
        padding: dp(20), dp(12)
        spacing: dp(2)
        canvas.before:
            Color:
                rgba: app.header_color
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            text: "DocConvert NCTS"
            font_size: "21sp"
            bold: True
            halign: "left"
            valign: "middle"
            text_size: self.size
            color: 1, 1, 1, 1

        Label:
            text: "Convierte documentos de forma privada y local"
            font_size: "12sp"
            halign: "left"
            valign: "middle"
            text_size: self.size
            color: 0.68, 0.72, 0.85, 1

    ScrollView:
        do_scroll_x: False

        BoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            padding: dp(16)
            spacing: dp(14)

            # --- Selector de modo ---
            BoxLayout:
                size_hint_y: None
                height: dp(48)
                spacing: dp(6)
                canvas.before:
                    Color:
                        rgba: app.card_color
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(12)]
                padding: dp(4)

                Button:
                    text: "PDF -> Word"
                    font_size: "13sp"
                    bold: app.mode == "pdf_to_word"
                    background_normal: ""
                    background_color: app.accent_color if app.mode == "pdf_to_word" else (0, 0, 0, 0)
                    color: 1, 1, 1, 1
                    on_release: app.set_mode("pdf_to_word")

                Button:
                    text: "Word -> PDF"
                    font_size: "13sp"
                    bold: app.mode == "word_to_pdf"
                    background_normal: ""
                    background_color: app.accent_color if app.mode == "word_to_pdf" else (0, 0, 0, 0)
                    color: 1, 1, 1, 1
                    on_release: app.set_mode("word_to_pdf")

            # --- Selección ---
            Button:
                text: app.mode_select_label
                size_hint_y: None
                height: dp(56)
                font_size: "16sp"
                bold: True
                background_normal: ""
                background_color: app.accent_color
                color: 1, 1, 1, 1
                on_release: app.open_file_chooser()

            Label:
                text: "Máx. {} MB por archivo".format(app.max_size_mb)
                size_hint_y: None
                height: dp(16)
                font_size: "10sp"
                color: app.text_muted
                halign: "center"
                text_size: self.size

            # --- Archivos ---
            SectionLabel:
                text: "Archivos ({})".format(len(app.files)) if app.files else "Archivos"

            Label:
                text: app.mode_empty_hint
                size_hint_y: None
                height: dp(24) if not app.files else 0
                opacity: 1 if not app.files else 0
                color: app.text_muted
                font_size: "12sp"
                halign: "left"
                text_size: self.size

            BoxLayout:
                id: file_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(10)

            # --- Estado global / cancelar ---
            Label:
                text: app.status_text
                size_hint_y: None
                height: max(dp(20), self.texture_size[1]) if app.status_text else 0
                text_size: self.width, None
                color: app.text_secondary
                halign: "left"
                valign: "top"
                font_size: "12sp"

            Button:
                text: "Cancelar conversión"
                size_hint_y: None
                height: dp(42) if app.converting else 0
                opacity: 1 if app.converting else 0
                disabled: not app.converting
                font_size: "13sp"
                background_normal: ""
                background_color: 0.5, 0.2, 0.2, 1
                color: 1, 1, 1, 1
                on_release: app.cancel_conversion()

            # --- Botón principal ---
            Button:
                text: "Convertir archivos"
                size_hint_y: None
                height: dp(56)
                font_size: "16sp"
                bold: True
                disabled: not app.files or app.converting
                background_normal: ""
                background_color: app.accent_color if (app.files and not app.converting) else (0.25, 0.27, 0.32, 1)
                color: 1, 1, 1, 1
                on_release: app.start_conversion()

            Button:
                text: "Limpiar lista"
                size_hint_y: None
                height: dp(40)
                font_size: "13sp"
                background_normal: ""
                background_color: 0.2, 0.21, 0.26, 1
                color: app.text_secondary
                on_release: app.clear_files()

            # --- Historial ---
            SectionLabel:
                text: "Conversiones recientes"
                padding: 0, dp(8), 0, 0

            Label:
                text: "Aún no hay conversiones" if not app.history else ""
                size_hint_y: None
                height: dp(20) if not app.history else 0
                color: app.text_muted
                font_size: "12sp"
                halign: "left"
                text_size: self.size

            BoxLayout:
                id: history_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(6)

            # --- Avisos ---
            Label:
                text: "Los documentos complejos pueden presentar cambios de formato respecto al original."
                size_hint_y: None
                height: dp(32)
                font_size: "11sp"
                color: app.warning_color
                halign: "left"
                valign: "top"
                text_size: self.width, None

            Label:
                text: "Tus archivos se procesan en el dispositivo. Nada se sube a internet."
                size_hint_y: None
                height: dp(28)
                font_size: "11sp"
                color: app.text_muted
                halign: "left"
                valign: "top"
                text_size: self.width, None
"""


class FileRow(BoxLayout):
    file_path = StringProperty("")
    file_name = StringProperty("")
    file_size = StringProperty("")
    mode_label = StringProperty("")
    output_path = StringProperty("")
    status_text = StringProperty("Pendiente")
    status_color = ListProperty([0.55, 0.57, 0.63, 1])
    progress = NumericProperty(0)

    def on_remove(self, path):
        App.get_running_app().remove_file(path)

    def on_open(self):
        if self.output_path:
            App.get_running_app().open_output_file(self.output_path)

    def on_share(self):
        if self.output_path:
            App.get_running_app().share_output_file(self.output_path)


class DocConvertApp(App):
    files = ListProperty([])
    converting = BooleanProperty(False)
    cancel_requested = BooleanProperty(False)
    status_text = StringProperty("")
    mode = StringProperty(MODE_PDF_TO_WORD)
    history = ListProperty([])

    mode_select_label = StringProperty(MODE_INFO[MODE_PDF_TO_WORD]["select_label"])
    mode_empty_hint = StringProperty(MODE_INFO[MODE_PDF_TO_WORD]["empty_hint"])
    max_size_mb = NumericProperty(MAX_FILE_SIZE_MB)

    bg_color = ListProperty(list(BG))
    header_color = ListProperty(list(HEADER))
    card_color = ListProperty(list(CARD))
    accent_color = ListProperty(list(ACCENT))
    warning_color = ListProperty(list(WARNING))
    text_primary = ListProperty(list(TEXT_PRIMARY))
    text_secondary = ListProperty(list(TEXT_SECONDARY))
    text_muted = ListProperty(list(TEXT_MUTED))

    # ------------------------------------------------------------ Setup
    def build(self):
        self.rows = {}
        self.display_names = {}
        self.output_paths = {}
        self.history_rows = []
        self.output_dir = None
        root = Builder.load_string(KV)
        return root

    def on_start(self):
        ensure_permissions(self._on_permissions_result)
        Window.bind(on_keyboard=self._on_keyboard)
        self._load_history()

    def _on_keyboard(self, window, key, *args):
        # key 27 = botón físico "atrás" de Android
        if key == 27 and self.converting:
            self.status_text = "Espera a que termine (o cancela) antes de salir."
            return True
        return False

    def _on_permissions_result(self, granted: bool):
        self.output_dir = default_output_dir()
        if not granted:
            self.status_text = (
                "Sin permisos de almacenamiento: no se podrán guardar los archivos convertidos."
            )

    # --------------------------------------------------------- Modo
    def set_mode(self, new_mode):
        if self.converting or new_mode == self.mode:
            return
        self.mode = new_mode
        info = MODE_INFO[new_mode]
        self.mode_select_label = info["select_label"]
        self.mode_empty_hint = info["empty_hint"]
        self.clear_files()

    # --------------------------------------------------------- Selección
    def open_file_chooser(self):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self._on_files_selected,
                multiple=True,
                filters=MODE_INFO[self.mode]["filters"],
            )
        except Exception as exc:
            self.status_text = f"No se pudo abrir el selector de archivos: {exc}"

    def _on_files_selected(self, selection):
        if not selection:
            return
        added = 0
        rejected = []
        for path in selection:
            if path in self.files:
                continue

            size = get_file_size(path)
            if size is not None and size > MAX_FILE_SIZE_BYTES:
                rejected.append(get_display_name(path))
                continue

            self.files.append(path)
            self.display_names[path] = get_display_name(path)
            self._add_row(path, size)
            added += 1

        messages = []
        if added:
            messages.append(f"{added} archivo(s) agregado(s).")
        if rejected:
            messages.append(
                f"Se omitieron {len(rejected)} archivo(s) por superar {MAX_FILE_SIZE_MB} MB: "
                + ", ".join(rejected)
            )
        if messages:
            self.status_text = " ".join(messages)

    def _add_row(self, path, size=None):
        from kivy.factory import Factory

        row = Factory.FileRow()
        row.file_path = path
        row.file_name = self.display_names.get(path, Path(path).name)
        row.file_size = format_file_size(size if size is not None else get_file_size(path))
        row.mode_label = MODE_INFO[self.mode]["label"]
        self.rows[path] = row
        self.root.ids.file_list.add_widget(row)

    def remove_file(self, path):
        if path in self.files:
            self.files.remove(path)
        self.display_names.pop(path, None)
        self.output_paths.pop(path, None)
        row = self.rows.pop(path, None)
        if row:
            self.root.ids.file_list.remove_widget(row)

    def clear_files(self):
        if self.converting:
            return
        for path in list(self.files):
            self.remove_file(path)
        self.status_text = ""

    def cancel_conversion(self):
        if self.converting:
            self.cancel_requested = True
            self.status_text = "Cancelando... se detendrá después del archivo actual."

    # -------------------------------------------------------- Conversión
    def start_conversion(self):
        if not self.files or self.converting:
            return

        self.converting = True
        self.cancel_requested = False
        self.status_text = "Iniciando conversión..."

        thread = threading.Thread(target=self._convert_worker, daemon=True)
        thread.start()

    def _convert_worker(self):
        completed = 0
        errored = 0
        output_dir = ""
        cache_dir = temp_cache_dir()

        # Todo el cuerpo va en try/finally: si algo falla antes de llegar al
        # try interno de cada archivo, igual se garantiza que _finish() se
        # ejecute y la interfaz nunca se quede congelada.
        try:
            output_dir = self.output_dir or default_output_dir()
            out_ext = MODE_INFO[self.mode]["out_ext"]
            mode_label = MODE_INFO[self.mode]["label"]

            for index, path in enumerate(list(self.files)):
                if self.cancel_requested:
                    self._update_row_status(path, "Cancelado", (0.6, 0.6, 0.35, 1))
                    continue

                display_name = self.display_names.get(path, Path(path).name)
                local_path = None
                try:
                    name_without_ext = Path(display_name).stem or "documento"
                    output_path = os.path.join(output_dir, f"{name_without_ext}{out_ext}")

                    self._update_row_status(path, "Convirtiendo...", (0.35, 0.55, 0.95, 1))
                    self._update_row_progress(path, 0.15)
                    self._set_status(f"Convirtiendo: {display_name}")

                    local_path = resolve_to_local_path(path, cache_dir)
                    self._update_row_progress(path, 0.45)

                    def progress_cb(msg, p=display_name, path_ref=path):
                        self._set_status(f"{p}: {msg}")
                        self._update_row_progress(path_ref, 0.75)

                    if self.mode == MODE_PDF_TO_WORD:
                        convert_pdf_to_word(local_path, output_path, progress_cb=progress_cb)
                    else:
                        convert_word_to_pdf(local_path, output_path, progress_cb=progress_cb)

                    notify_media_scanner(output_path)
                    self.output_paths[path] = output_path
                    self._update_row_output(path, output_path)
                    self._update_row_status(path, "Completado", (0.3, 0.75, 0.5, 1))
                    self._update_row_progress(path, 1.0)
                    self._add_history(display_name, mode_label, "Completado")
                    completed += 1
                except ConversionError as exc:
                    self._update_row_status(path, "Error", (0.9, 0.35, 0.38, 1))
                    self._update_row_progress(path, 0)
                    self._show_error(display_name, str(exc))
                    self._add_history(display_name, mode_label, "Error")
                    errored += 1
                except Exception as exc:
                    self._update_row_status(path, "Error", (0.9, 0.35, 0.38, 1))
                    self._update_row_progress(path, 0)
                    self._show_error(display_name, f"Error inesperado: {exc}")
                    self._add_history(display_name, mode_label, "Error")
                    errored += 1
                finally:
                    # Limpieza: si tuvimos que copiar un content:// URI a un
                    # archivo temporal, lo borramos (nunca borra el original).
                    if local_path and local_path != path:
                        cleanup_temp_file(local_path, cache_dir)
        except Exception as exc:
            self._set_status(f"Error inesperado durante la conversión: {exc}")
        finally:
            self._finish(completed, errored, output_dir)

    # --------------------------------------------------- Actualizaciones UI
    @mainthread
    def _update_row_status(self, path, text, color):
        row = self.rows.get(path)
        if row:
            row.status_text = text
            row.status_color = list(color)

    @mainthread
    def _update_row_progress(self, path, value):
        row = self.rows.get(path)
        if row:
            row.progress = value

    @mainthread
    def _update_row_output(self, path, output_path):
        row = self.rows.get(path)
        if row:
            row.output_path = output_path

    @mainthread
    def _set_status(self, text):
        self.status_text = text

    @mainthread
    def _finish(self, completed, errored, output_dir):
        self.converting = False
        self.cancel_requested = False
        if completed or errored:
            self.status_text = (
                f"Terminado: {completed} completado(s), {errored} con error. "
                f"Guardado en: {output_dir}"
            )
        else:
            self.status_text = "Conversión cancelada."

    @mainthread
    def _show_error(self, filename, message):
        from kivy.uix.label import Label

        popup = Popup(title=f"Error al convertir {filename}", size_hint=(0.85, 0.4))
        popup.content = Label(text=message, text_size=(Window.width * 0.7, None))
        popup.open()

    @mainthread
    def _show_info(self, message):
        from kivy.uix.label import Label

        popup = Popup(title="DocConvert NCTS", size_hint=(0.85, 0.35))
        popup.content = Label(text=message, text_size=(Window.width * 0.7, None))
        popup.open()

    # ---------------------------------------------------------- Abrir/compartir
    def open_output_file(self, output_path):
        if not output_path or not os.path.isfile(output_path):
            self._show_info("Ese archivo ya no está disponible (¿se movió o se borró?).")
            return
        opened = open_file_external(output_path)
        if not opened:
            self._show_info(f"Archivo guardado en:\n{output_path}")

    def share_output_file(self, output_path):
        if not output_path or not os.path.isfile(output_path):
            self._show_info("Ese archivo ya no está disponible (¿se movió o se borró?).")
            return
        shared = share_file_external(output_path)
        if not shared:
            self._show_info(f"No se pudo abrir el menú de compartir. Archivo en:\n{output_path}")

    # ------------------------------------------------------------- Historial
    def _load_history(self):
        self._apply_history(history.load_history())

    def _add_history(self, name, mode_label, status):
        updated = history.add_entry(name, mode_label, status)
        self._apply_history(updated)

    @mainthread
    def _apply_history(self, updated_history):
        from kivy.factory import Factory

        self.history = updated_history
        container = self.root.ids.history_list
        container.clear_widgets()
        for entry in self.history:
            row = Factory.HistoryRow()
            row.name = entry.get("name", "")
            row.mode = entry.get("mode", "")
            row.status = entry.get("status", "")
            row.timestamp = entry.get("timestamp", "")
            container.add_widget(row)


if __name__ == "__main__":
    DocConvertApp().run()
