"""
DocConvert NCTS - Móvil
Convierte PDF -> Word directamente en tu Android, sin subir archivos a internet.
"""

import os
import threading
from pathlib import Path

from kivy.app import App
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from android_utils import default_output_dir, ensure_permissions, notify_media_scanner
from converter import ConversionError, convert_pdf_to_word

Window.clearcolor = (0.97, 0.97, 0.98, 1)

KV = """
#:import dp kivy.metrics.dp

<FileRow@BoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(56)
    padding: dp(10), dp(6)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]

    Label:
        text: root.file_name
        color: 0.1, 0.1, 0.15, 1
        halign: "left"
        valign: "middle"
        text_size: self.size
        shorten: True
        shorten_from: "right"

    Label:
        id: status_label
        text: root.status_text
        color: root.status_color
        size_hint_x: None
        width: dp(110)
        halign: "right"
        valign: "middle"
        text_size: self.size

    Button:
        text: "x"
        size_hint_x: None
        width: dp(44)
        font_size: "16sp"
        background_normal: ""
        background_color: 0.85, 0.3, 0.3, 1
        color: 1, 1, 1, 1
        on_release: root.on_remove(root.file_path)

BoxLayout:
    orientation: "vertical"

    # --- Encabezado ---
    BoxLayout:
        size_hint_y: None
        height: dp(96)
        padding: dp(18), dp(14)
        canvas.before:
            Color:
                rgba: 0.11, 0.15, 0.24, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: "vertical"
            Label:
                text: "DocConvert NCTS"
                font_size: "20sp"
                bold: True
                halign: "left"
                text_size: self.size
                color: 1, 1, 1, 1
            Label:
                text: "PDF -> Word, 100% local"
                font_size: "13sp"
                halign: "left"
                text_size: self.size
                color: 0.75, 0.8, 0.9, 1

    # --- Cuerpo ---
    BoxLayout:
        orientation: "vertical"
        padding: dp(16)
        spacing: dp(12)

        Button:
            text: "Seleccionar PDF(s)"
            size_hint_y: None
            height: dp(52)
            background_normal: ""
            background_color: 0.16, 0.45, 0.85, 1
            color: 1, 1, 1, 1
            font_size: "16sp"
            on_release: app.open_file_chooser()

        Label:
            text: "Archivos" if app.files else "Aún no has agregado archivos"
            size_hint_y: None
            height: dp(24)
            color: 0.3, 0.3, 0.35, 1
            halign: "left"
            text_size: self.size

        ScrollView:
            BoxLayout:
                id: file_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(6)

        Label:
            text: app.status_text
            size_hint_y: None
            height: max(dp(24), self.texture_size[1])
            text_size: self.width, None
            color: 0.25, 0.25, 0.3, 1
            halign: "left"
            valign: "top"
            font_size: "13sp"

        ProgressBar:
            id: progress_bar
            size_hint_y: None
            height: dp(8)
            max: 1
            value: 0

        BoxLayout:
            size_hint_y: None
            height: dp(52)
            spacing: dp(10)

            Button:
                text: "Limpiar"
                background_normal: ""
                background_color: 0.6, 0.6, 0.65, 1
                color: 1, 1, 1, 1
                on_release: app.clear_files()

            Button:
                text: "Convertir"
                disabled: not app.files or app.converting
                background_normal: ""
                background_color: (0.2, 0.7, 0.4, 1) if self.disabled == False else (0.75, 0.8, 0.78, 1)
                color: 1, 1, 1, 1
                font_size: "16sp"
                on_release: app.start_conversion()

        Label:
            text: "Tus archivos se procesan en el dispositivo. Nada se sube a internet."
            size_hint_y: None
            height: dp(22)
            font_size: "11sp"
            color: 0.5, 0.5, 0.55, 1
            halign: "left"
            text_size: self.size
"""


class FileRow(BoxLayout):
    file_path = StringProperty("")
    file_name = StringProperty("")
    status_text = StringProperty("Pendiente")
    status_color = ListProperty([0.5, 0.5, 0.5, 1])

    def on_remove(self, path):
        App.get_running_app().remove_file(path)


class DocConvertApp(App):
    files = ListProperty([])
    converting = BooleanProperty(False)
    status_text = StringProperty("")

    def build(self):
        self.rows = {}
        self.output_dir = None
        root = Builder.load_string(KV)
        return root

    def on_start(self):
        ensure_permissions(self._on_permissions_result)
        Window.bind(on_keyboard=self._on_keyboard)

    def _on_keyboard(self, window, key, *args):
        # key 27 = botón físico "atrás" de Android
        if key == 27 and self.converting:
            self.status_text = "Espera a que termine la conversión antes de salir."
            return True  # bloquea el cierre
        return False

    def _on_permissions_result(self, granted: bool):
        self.output_dir = default_output_dir()
        if not granted:
            self.status_text = (
                "Sin permisos de almacenamiento: no se podrán guardar los archivos convertidos."
            )

    # --------------------------------------------------------- Selección
    def open_file_chooser(self):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self._on_files_selected,
                multiple=True,
                filters=[("Documentos PDF", "*.pdf")],
            )
        except Exception as exc:
            self.status_text = f"No se pudo abrir el selector de archivos: {exc}"

    def _on_files_selected(self, selection):
        if not selection:
            return
        added = 0
        for path in selection:
            if path.lower().endswith(".pdf") and path not in self.files:
                self.files.append(path)
                self._add_row(path)
                added += 1
        if added:
            self.status_text = f"{added} archivo(s) agregado(s)."

    def _add_row(self, path):
        from kivy.factory import Factory

        row = Factory.FileRow()
        row.file_path = path
        row.file_name = Path(path).name
        self.rows[path] = row
        self.root.ids.file_list.add_widget(row)

    def remove_file(self, path):
        if path in self.files:
            self.files.remove(path)
        row = self.rows.pop(path, None)
        if row:
            self.root.ids.file_list.remove_widget(row)

    def clear_files(self):
        if self.converting:
            return
        for path in list(self.files):
            self.remove_file(path)
        self.status_text = ""
        self.root.ids.progress_bar.value = 0

    # -------------------------------------------------------- Conversión
    def start_conversion(self):
        if not self.files or self.converting:
            return

        self.converting = True
        self.root.ids.progress_bar.max = len(self.files)
        self.root.ids.progress_bar.value = 0
        self.status_text = "Iniciando conversión..."

        thread = threading.Thread(target=self._convert_worker, daemon=True)
        thread.start()

    def _convert_worker(self):
        completed = 0
        errored = 0
        output_dir = self.output_dir or default_output_dir()

        for index, path in enumerate(list(self.files)):
            name = Path(path).stem
            output_path = os.path.join(output_dir, f"{name}.docx")

            self._update_row_status(path, "Convirtiendo...", (0.16, 0.45, 0.85, 1))
            self._set_status(f"Convirtiendo: {Path(path).name}")

            try:
                convert_pdf_to_word(
                    path,
                    output_path,
                    progress_cb=lambda msg, p=path: self._set_status(f"{Path(p).name}: {msg}"),
                )
                notify_media_scanner(output_path)
                self._update_row_status(path, "Completado", (0.2, 0.6, 0.3, 1))
                completed += 1
            except ConversionError as exc:
                self._update_row_status(path, "Error", (0.8, 0.2, 0.2, 1))
                self._show_error(Path(path).name, str(exc))
                errored += 1
            except Exception as exc:
                self._update_row_status(path, "Error", (0.8, 0.2, 0.2, 1))
                self._show_error(Path(path).name, f"Error inesperado: {exc}")
                errored += 1

            self._advance_progress(index + 1)

        self._finish(completed, errored, output_dir)

    @mainthread
    def _update_row_status(self, path, text, color):
        row = self.rows.get(path)
        if row:
            row.status_text = text
            row.status_color = list(color)

    @mainthread
    def _set_status(self, text):
        self.status_text = text

    @mainthread
    def _advance_progress(self, done):
        self.root.ids.progress_bar.value = done

    @mainthread
    def _show_error(self, filename, message):
        popup = Popup(
            title=f"Error al convertir {filename}",
            size_hint=(0.85, 0.4),
        )
        from kivy.uix.label import Label

        popup.content = Label(text=message, text_size=(Window.width * 0.7, None))
        popup.open()

    @mainthread
    def _finish(self, completed, errored, output_dir):
        self.converting = False
        self.status_text = (
            f"Terminado: {completed} completado(s), {errored} con error. "
            f"Guardado en: {output_dir}"
        )


if __name__ == "__main__":
    DocConvertApp().run()
