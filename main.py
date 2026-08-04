"""
DocConvert NCTS - Móvil
Convierte PDF <-> Word y Fotos -> PDF directamente en tu Android.
100% local, sin internet. Administra los archivos que ya creaste.
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
    delete_file,
    ensure_camera_permission,
    ensure_permissions,
    format_file_size,
    get_display_name,
    get_file_size,
    notify_media_scanner,
    open_file_external,
    rename_file,
    resolve_to_local_path,
    resolve_unique_path,
    sanitize_filename,
    share_file_external,
    take_photo,
    temp_cache_dir,
)
from converter import ConversionError, convert_pdf_to_word
from image_converter import convert_images_to_pdf, rotate_image_file
from word_converter import convert_word_to_pdf

# ------------------------------------------------------------------ Tema
BG = (0.06, 0.07, 0.10, 1)
CARD = (0.11, 0.12, 0.17, 1)
HEADER = (0.05, 0.06, 0.09, 1)
ACCENT = (0.30, 0.50, 0.95, 1)
SUCCESS = (0.20, 0.70, 0.45, 1)
ERROR = (0.90, 0.35, 0.38, 1)
WARNING = (0.90, 0.65, 0.25, 1)
TEXT_PRIMARY = (0.95, 0.95, 0.97, 1)
TEXT_SECONDARY = (0.68, 0.70, 0.78, 1)
TEXT_MUTED = (0.48, 0.50, 0.58, 1)

Window.clearcolor = BG

MODE_PDF_TO_WORD = "pdf_to_word"
MODE_WORD_TO_PDF = "word_to_pdf"
MODE_PHOTOS_TO_PDF = "photos_to_pdf"

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
    MODE_PHOTOS_TO_PDF: {
        "label": "Fotos -> PDF",
        "select_label": "Elegir de galería",
        "filters": [("Imágenes", "*.jpg"), ("Imágenes", "*.jpeg"), ("Imágenes", "*.png")],
        "out_ext": ".pdf",
        "empty_hint": "Aún no has agregado fotos",
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
            disabled: app.converting
            background_normal: ""
            background_color: 0.5, 0.18, 0.2, 1
            color: 1, 1, 1, 1
            on_release: root.on_remove(root.file_path)


<PhotoRow>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(84)
    padding: dp(10)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: app.card_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

    Image:
        source: root.photo_path
        size_hint: None, None
        size: dp(64), dp(64)
        allow_stretch: True
        keep_ratio: True

    BoxLayout:
        orientation: "vertical"
        Label:
            text: root.file_name
            color: app.text_primary
            font_size: "12sp"
            halign: "left"
            valign: "middle"
            text_size: self.size
            shorten: True
            shorten_from: "right"
        Label:
            text: "Foto " + str(root.position)
            color: app.text_muted
            font_size: "10sp"
            halign: "left"
            valign: "middle"
            text_size: self.size

    BoxLayout:
        orientation: "vertical"
        size_hint_x: None
        width: dp(46)
        spacing: dp(2)
        Button:
            text: "Arriba"
            font_size: "9sp"
            disabled: app.converting
            background_normal: ""
            background_color: 0.22, 0.24, 0.30, 1
            color: 1, 1, 1, 1
            on_release: root.on_move_up()
        Button:
            text: "Abajo"
            font_size: "9sp"
            disabled: app.converting
            background_normal: ""
            background_color: 0.22, 0.24, 0.30, 1
            color: 1, 1, 1, 1
            on_release: root.on_move_down()

    BoxLayout:
        orientation: "vertical"
        size_hint_x: None
        width: dp(52)
        spacing: dp(2)
        Button:
            text: "Rotar"
            font_size: "9sp"
            disabled: app.converting
            background_normal: ""
            background_color: 0.22, 0.4, 0.75, 1
            color: 1, 1, 1, 1
            on_release: root.on_rotate()
        Button:
            text: "Quitar"
            font_size: "9sp"
            disabled: app.converting
            background_normal: ""
            background_color: 0.5, 0.18, 0.2, 1
            color: 1, 1, 1, 1
            on_release: root.on_remove()


<HistoryCard>:
    orientation: "vertical"
    size_hint_y: None
    height: dp(112)
    padding: dp(12)
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: app.card_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

    BoxLayout:
        orientation: "horizontal"
        size_hint_y: None
        height: dp(20)
        Label:
            text: root.name
            color: app.text_primary
            font_size: "13sp"
            bold: True
            halign: "left"
            valign: "middle"
            text_size: self.size
            shorten: True
            shorten_from: "right"
        Label:
            text: root.size_text
            color: app.text_muted
            size_hint_x: None
            width: dp(60)
            font_size: "11sp"
            halign: "right"
            valign: "middle"
            text_size: self.size

    Label:
        text: root.mode + "  -  " + root.timestamp
        size_hint_y: None
        height: dp(16)
        color: app.text_muted
        font_size: "10sp"
        halign: "left"
        valign: "middle"
        text_size: self.size

    Label:
        text: root.status
        size_hint_y: None
        height: dp(16)
        font_size: "11sp"
        color: (0.2, 0.7, 0.45, 1) if root.status == "Completado" else (0.85, 0.4, 0.4, 1)
        halign: "left"
        valign: "middle"
        text_size: self.size

    BoxLayout:
        orientation: "horizontal"
        size_hint_y: None
        height: dp(30)
        spacing: dp(6)
        padding: 0, dp(4), 0, 0

        Button:
            text: "Abrir"
            font_size: "11sp"
            disabled: root.status != "Completado"
            background_normal: ""
            background_color: (0.2, 0.55, 0.35, 1) if root.status == "Completado" else (0.2, 0.21, 0.26, 1)
            color: 1, 1, 1, 1
            on_release: root.on_open()

        Button:
            text: "Compartir"
            font_size: "11sp"
            disabled: root.status != "Completado"
            background_normal: ""
            background_color: (0.22, 0.4, 0.75, 1) if root.status == "Completado" else (0.2, 0.21, 0.26, 1)
            color: 1, 1, 1, 1
            on_release: root.on_share()

        Button:
            text: "Más"
            font_size: "11sp"
            size_hint_x: 0.6
            background_normal: ""
            background_color: 0.22, 0.24, 0.30, 1
            color: 1, 1, 1, 1
            on_release: root.on_more()


BoxLayout:
    orientation: "vertical"
    canvas.before:
        Color:
            rgba: app.bg_color
        Rectangle:
            pos: self.pos
            size: self.size

    # --- Encabezado compacto ---
    BoxLayout:
        orientation: "vertical"
        size_hint_y: None
        height: dp(64)
        padding: dp(20), dp(10)
        spacing: dp(2)
        canvas.before:
            Color:
                rgba: app.header_color
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            text: "DocConvert NCTS"
            font_size: "19sp"
            bold: True
            halign: "left"
            valign: "middle"
            text_size: self.size
            color: 1, 1, 1, 1

        Label:
            text: "Convierte y administra tus documentos"
            font_size: "11sp"
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

            # --- Mis archivos creados ---
            SectionLabel:
                text: "Mis archivos creados ({})".format(len(app.history)) if app.history else "Mis archivos creados"

            Label:
                text: "Aún no has creado ningún archivo.\\nConvierte tu primer documento para verlo aquí."
                size_hint_y: None
                height: dp(44) if not app.history else 0
                opacity: 1 if not app.history else 0
                color: app.text_muted
                font_size: "12sp"
                halign: "left"
                valign: "top"
                text_size: self.size

            BoxLayout:
                id: history_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(8)

            Widget:
                size_hint_y: None
                height: dp(6)

            # --- Selector de modo (3 pestañas) ---
            SectionLabel:
                text: "Nueva conversión"

            BoxLayout:
                size_hint_y: None
                height: dp(48)
                spacing: dp(4)
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
                    font_size: "11sp"
                    bold: app.mode == "pdf_to_word"
                    disabled: app.converting
                    background_normal: ""
                    background_color: app.accent_color if app.mode == "pdf_to_word" else (0, 0, 0, 0)
                    color: 1, 1, 1, 1
                    on_release: app.set_mode("pdf_to_word")

                Button:
                    text: "Word -> PDF"
                    font_size: "11sp"
                    bold: app.mode == "word_to_pdf"
                    disabled: app.converting
                    background_normal: ""
                    background_color: app.accent_color if app.mode == "word_to_pdf" else (0, 0, 0, 0)
                    color: 1, 1, 1, 1
                    on_release: app.set_mode("word_to_pdf")

                Button:
                    text: "Fotos -> PDF"
                    font_size: "11sp"
                    bold: app.mode == "photos_to_pdf"
                    disabled: app.converting
                    background_normal: ""
                    background_color: app.accent_color if app.mode == "photos_to_pdf" else (0, 0, 0, 0)
                    color: 1, 1, 1, 1
                    on_release: app.set_mode("photos_to_pdf")

            # --- Selección: documentos (PDF/Word) ---
            Button:
                text: app.mode_select_label
                size_hint_y: None
                height: dp(52) if app.mode != "photos_to_pdf" else 0
                opacity: 1 if app.mode != "photos_to_pdf" else 0
                disabled: app.converting or app.mode == "photos_to_pdf"
                font_size: "15sp"
                bold: True
                background_normal: ""
                background_color: app.accent_color
                color: 1, 1, 1, 1
                on_release: app.open_file_chooser()

            # --- Selección: fotos ---
            BoxLayout:
                size_hint_y: None
                height: dp(52) if app.mode == "photos_to_pdf" else 0
                opacity: 1 if app.mode == "photos_to_pdf" else 0
                disabled: app.converting or app.mode != "photos_to_pdf"
                spacing: dp(8)

                Button:
                    text: "Elegir de galería"
                    font_size: "13sp"
                    bold: True
                    disabled: app.converting
                    background_normal: ""
                    background_color: app.accent_color
                    color: 1, 1, 1, 1
                    on_release: app.open_file_chooser()

                Button:
                    text: "Tomar foto"
                    font_size: "13sp"
                    bold: True
                    disabled: app.converting
                    background_normal: ""
                    background_color: 0.2, 0.55, 0.4, 1
                    color: 1, 1, 1, 1
                    on_release: app.take_photo_now()

            Label:
                text: "Máx. {} MB por archivo".format(app.max_size_mb)
                size_hint_y: None
                height: dp(16)
                font_size: "10sp"
                color: app.text_muted
                halign: "center"
                text_size: self.size

            # --- Opciones de fotos: tamaño de página y calidad ---
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: dp(96) if app.mode == "photos_to_pdf" and app.files else 0
                opacity: 1 if (app.mode == "photos_to_pdf" and app.files) else 0
                spacing: dp(6)

                BoxLayout:
                    size_hint_y: None
                    height: dp(40)
                    spacing: dp(6)

                    Button:
                        text: "Pagina A4"
                        font_size: "11sp"
                        disabled: app.converting
                        background_normal: ""
                        background_color: app.accent_color if app.page_size == "A4" else app.card_color
                        color: 1, 1, 1, 1
                        on_release: app.set_page_size("A4")

                    Button:
                        text: "Pagina Carta"
                        font_size: "11sp"
                        disabled: app.converting
                        background_normal: ""
                        background_color: app.accent_color if app.page_size == "Carta" else app.card_color
                        color: 1, 1, 1, 1
                        on_release: app.set_page_size("Carta")

                BoxLayout:
                    size_hint_y: None
                    height: dp(40)
                    spacing: dp(6)

                    Button:
                        text: "Calidad Baja"
                        font_size: "11sp"
                        disabled: app.converting
                        background_normal: ""
                        background_color: app.accent_color if app.quality == "Baja" else app.card_color
                        color: 1, 1, 1, 1
                        on_release: app.set_quality("Baja")

                    Button:
                        text: "Calidad Media"
                        font_size: "11sp"
                        disabled: app.converting
                        background_normal: ""
                        background_color: app.accent_color if app.quality == "Media" else app.card_color
                        color: 1, 1, 1, 1
                        on_release: app.set_quality("Media")

                    Button:
                        text: "Calidad Alta"
                        font_size: "11sp"
                        disabled: app.converting
                        background_normal: ""
                        background_color: app.accent_color if app.quality == "Alta" else app.card_color
                        color: 1, 1, 1, 1
                        on_release: app.set_quality("Alta")

            TextInput:
                id: filename_input
                text: app.output_filename
                on_text: app.output_filename = self.text
                hint_text: "Nombre del PDF (opcional)"
                size_hint_y: None
                height: dp(44) if app.mode == "photos_to_pdf" and app.files else 0
                opacity: 1 if (app.mode == "photos_to_pdf" and app.files) else 0
                disabled: app.converting
                multiline: False
                font_size: "13sp"
                padding: dp(10), dp(12)
                background_normal: ""
                background_color: app.card_color
                foreground_color: app.text_primary
                cursor_color: app.text_primary

            # --- Lista de archivos seleccionados (documentos) ---
            SectionLabel:
                text: "Archivos seleccionados ({})".format(len(app.files)) if app.files else "Archivos seleccionados"
                height: dp(26) if app.mode != "photos_to_pdf" else 0
                opacity: 1 if app.mode != "photos_to_pdf" else 0

            Label:
                text: app.mode_empty_hint
                size_hint_y: None
                height: dp(24) if (not app.files and app.mode != "photos_to_pdf") else 0
                opacity: 1 if (not app.files and app.mode != "photos_to_pdf") else 0
                color: app.text_muted
                font_size: "12sp"
                halign: "left"
                text_size: self.size

            BoxLayout:
                id: file_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height if app.mode != "photos_to_pdf" else 0
                opacity: 1 if app.mode != "photos_to_pdf" else 0
                spacing: dp(10)

            # --- Lista de fotos seleccionadas ---
            SectionLabel:
                text: "Fotos seleccionadas ({})".format(len(app.files)) if app.files else "Fotos seleccionadas"
                height: dp(26) if app.mode == "photos_to_pdf" else 0
                opacity: 1 if app.mode == "photos_to_pdf" else 0

            Label:
                text: app.mode_empty_hint
                size_hint_y: None
                height: dp(24) if (not app.files and app.mode == "photos_to_pdf") else 0
                opacity: 1 if (not app.files and app.mode == "photos_to_pdf") else 0
                color: app.text_muted
                font_size: "12sp"
                halign: "left"
                text_size: self.size

            BoxLayout:
                id: photo_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height if app.mode == "photos_to_pdf" else 0
                opacity: 1 if app.mode == "photos_to_pdf" else 0
                spacing: dp(8)

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
                text: "Limpiar selección"
                size_hint_y: None
                height: dp(40)
                font_size: "13sp"
                disabled: app.converting
                background_normal: ""
                background_color: 0.2, 0.21, 0.26, 1
                color: app.text_secondary
                on_release: app.clear_files()

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


class PhotoRow(BoxLayout):
    photo_path = StringProperty("")
    file_name = StringProperty("")
    position = NumericProperty(1)

    def on_move_up(self):
        App.get_running_app().move_photo(self.photo_path, -1)

    def on_move_down(self):
        App.get_running_app().move_photo(self.photo_path, 1)

    def on_rotate(self):
        App.get_running_app().rotate_photo(self.photo_path)

    def on_remove(self):
        App.get_running_app().remove_file(self.photo_path)


class HistoryCard(BoxLayout):
    entry_id = StringProperty("")
    name = StringProperty("")
    mode = StringProperty("")
    status = StringProperty("")
    timestamp = StringProperty("")
    size_text = StringProperty("")
    output_path = StringProperty("")

    def on_open(self):
        App.get_running_app().open_output_file(self.output_path)

    def on_share(self):
        App.get_running_app().share_output_file(self.output_path)

    def on_more(self):
        App.get_running_app().open_history_actions(self.entry_id)


class DocConvertApp(App):
    files = ListProperty([])
    converting = BooleanProperty(False)
    cancel_requested = BooleanProperty(False)
    status_text = StringProperty("")
    mode = StringProperty(MODE_PDF_TO_WORD)
    history = ListProperty([])
    page_size = StringProperty("Carta")
    quality = StringProperty("Media")
    output_filename = StringProperty("")

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

    def set_page_size(self, size):
        if not self.converting:
            self.page_size = size

    def set_quality(self, quality):
        if not self.converting:
            self.quality = quality

    # --------------------------------------------------------- Selección
    def open_file_chooser(self):
        try:
            from plyer import filechooser

            multiple = True
            filechooser.open_file(
                on_selection=self._on_files_selected,
                multiple=multiple,
                filters=MODE_INFO[self.mode]["filters"],
            )
        except Exception as exc:
            self.status_text = f"No se pudo abrir el selector de archivos: {exc}"

    def take_photo_now(self):
        def _after_permission(granted):
            if not granted:
                self.status_text = "Sin permiso de cámara: no se puede tomar la foto."
                return
            started = take_photo(self._on_photo_taken)
            if not started:
                self.status_text = (
                    "La cámara no está disponible en este dispositivo/entorno."
                )

        ensure_camera_permission(_after_permission)

    def _on_photo_taken(self, photo_path):
        if photo_path:
            self._on_files_selected([photo_path])

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
            if self.mode == MODE_PHOTOS_TO_PDF:
                self._add_photo_row(path)
            else:
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

    def _add_photo_row(self, path):
        from kivy.factory import Factory

        # Las fotos de content:// hay que copiarlas a un archivo real para
        # poder mostrarlas como miniatura (Kivy Image no puede leer content://).
        local_path = resolve_to_local_path(path, temp_cache_dir())
        self.display_names[path] = self.display_names.get(path) or Path(local_path).name

        row = Factory.PhotoRow()
        row.photo_path = local_path
        row.file_name = self.display_names.get(path, Path(local_path).name)
        row.position = len(self.files)
        self.rows[path] = row
        self.root.ids.photo_list.add_widget(row)
        self._local_photo_paths = getattr(self, "_local_photo_paths", {})
        self._local_photo_paths[path] = local_path

    def _refresh_photo_positions(self):
        for index, path in enumerate(self.files):
            row = self.rows.get(path)
            if row:
                row.position = index + 1

    def move_photo(self, path, direction):
        if self.converting or path not in self.files:
            return
        index = self.files.index(path)
        new_index = index + direction
        if new_index < 0 or new_index >= len(self.files):
            return
        self.files[index], self.files[new_index] = self.files[new_index], self.files[index]

        container = self.root.ids.photo_list
        row = self.rows.get(path)
        if row:
            container.remove_widget(row)
            container.add_widget(row, index=len(container.children) - new_index)
        self._refresh_photo_positions()

    def rotate_photo(self, path):
        if self.converting:
            return
        local_path = getattr(self, "_local_photo_paths", {}).get(path, path)
        try:
            rotate_image_file(local_path, 90)
        except Exception as exc:
            self._show_info(f"No se pudo rotar la foto: {exc}")
            return

        # Kivy cachea imágenes por ruta; forzamos que se vuelva a leer el
        # archivo recién rotado en vez de mostrar la versión vieja en caché.
        from kivy.cache import Cache

        Cache.remove("kv.image")
        Cache.remove("kv.texture")
        row = self.rows.get(path)
        if row:
            row.photo_path = ""
            row.photo_path = local_path

    def remove_file(self, path):
        if path in self.files:
            self.files.remove(path)
        self.display_names.pop(path, None)
        self.output_paths.pop(path, None)
        if hasattr(self, "_local_photo_paths"):
            self._local_photo_paths.pop(path, None)
        row = self.rows.pop(path, None)
        if row:
            parent = row.parent
            if parent:
                parent.remove_widget(row)
        if self.mode == MODE_PHOTOS_TO_PDF:
            self._refresh_photo_positions()

    def clear_files(self):
        if self.converting:
            return
        for path in list(self.files):
            self.remove_file(path)
        self.status_text = ""
        self.output_filename = ""

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
        if self.mode == MODE_PHOTOS_TO_PDF:
            self._convert_worker_photos()
        else:
            self._convert_worker_documents()

    def _convert_worker_documents(self):
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
                temp_output_path = None
                try:
                    name_without_ext = Path(display_name).stem or "documento"
                    final_name = sanitize_filename(name_without_ext) + out_ext
                    final_output_path = resolve_unique_path(output_dir, final_name)
                    temp_output_path = final_output_path + ".part"

                    self._update_row_status(path, "Convirtiendo...", (0.35, 0.55, 0.95, 1))
                    self._update_row_progress(path, 0.15)
                    self._set_status(f"Convirtiendo: {display_name}")

                    local_path = resolve_to_local_path(path, cache_dir)
                    self._update_row_progress(path, 0.45)

                    def progress_cb(msg, p=display_name, path_ref=path):
                        self._set_status(f"{p}: {msg}")
                        self._update_row_progress(path_ref, 0.75)

                    if self.mode == MODE_PDF_TO_WORD:
                        convert_pdf_to_word(local_path, temp_output_path, progress_cb=progress_cb)
                    else:
                        convert_word_to_pdf(local_path, temp_output_path, progress_cb=progress_cb)

                    # Escritura "atómica": solo se renombra al nombre final
                    # una vez que la conversión terminó por completo. Así,
                    # si la app se cierra a la mitad, nunca queda un archivo
                    # corrupto con el nombre final -- en el peor caso queda
                    # un ".part" huérfano en la carpeta temporal, no en la
                    # carpeta de salida del usuario.
                    os.replace(temp_output_path, final_output_path)

                    notify_media_scanner(final_output_path)
                    self.output_paths[path] = final_output_path
                    self._update_row_output(path, final_output_path)
                    self._update_row_status(path, "Completado", (0.3, 0.75, 0.5, 1))
                    self._update_row_progress(path, 1.0)
                    self._add_history(
                        os.path.basename(final_output_path),
                        mode_label,
                        "Completado",
                        final_output_path,
                    )
                    self._notify_file_created(os.path.basename(final_output_path))
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
                    if local_path and local_path != path:
                        cleanup_temp_file(local_path, cache_dir)
                    if temp_output_path and os.path.isfile(temp_output_path):
                        try:
                            os.remove(temp_output_path)
                        except Exception:
                            pass
        except Exception as exc:
            self._set_status(f"Error inesperado durante la conversión: {exc}")
        finally:
            self._finish(completed, errored, output_dir)

    def _convert_worker_photos(self):
        output_dir = ""
        try:
            output_dir = self.output_dir or default_output_dir()
            mode_label = MODE_INFO[MODE_PHOTOS_TO_PDF]["label"]

            raw_name = sanitize_filename(self.output_filename or "Fotos a PDF")
            if not raw_name.lower().endswith(".pdf"):
                raw_name += ".pdf"
            final_output_path = resolve_unique_path(output_dir, raw_name)
            temp_output_path = final_output_path + ".part"

            local_paths = [
                getattr(self, "_local_photo_paths", {}).get(p, p) for p in list(self.files)
            ]

            def progress_cb(msg):
                self._set_status(msg)

            convert_images_to_pdf(
                local_paths,
                temp_output_path,
                page_size=self.page_size,
                quality=self.quality,
                progress_cb=progress_cb,
            )

            os.replace(temp_output_path, final_output_path)
            notify_media_scanner(final_output_path)
            self._add_history(
                os.path.basename(final_output_path),
                mode_label,
                "Completado",
                final_output_path,
            )
            self._notify_file_created(os.path.basename(final_output_path))
            self._finish(1, 0, output_dir)
        except ConversionError as exc:
            self._show_error("Fotos a PDF", str(exc))
            self._add_history(self.output_filename or "Fotos a PDF", "Fotos -> PDF", "Error")
            self._finish(0, 1, output_dir)
        except Exception as exc:
            self._show_error("Fotos a PDF", f"Error inesperado: {exc}")
            self._add_history(self.output_filename or "Fotos a PDF", "Fotos -> PDF", "Error")
            self._finish(0, 1, output_dir)

    # --------------------------------------------------- Actualizaciones UI
    @mainthread
    def _update_row_status(self, path, text, color):
        row = self.rows.get(path)
        if row and hasattr(row, "status_text"):
            row.status_text = text
            row.status_color = list(color)

    @mainthread
    def _update_row_progress(self, path, value):
        row = self.rows.get(path)
        if row and hasattr(row, "progress"):
            row.progress = value

    @mainthread
    def _update_row_output(self, path, output_path):
        row = self.rows.get(path)
        if row and hasattr(row, "output_path"):
            row.output_path = output_path

    @mainthread
    def _set_status(self, text):
        self.status_text = text

    @mainthread
    def _notify_file_created(self, filename):
        self._show_info(f"Archivo creado correctamente\n\n{filename}")

    @mainthread
    def _finish(self, completed, errored, output_dir):
        self.converting = False
        self.cancel_requested = False
        if self.mode == MODE_PHOTOS_TO_PDF and completed:
            # En fotos, solo limpiamos la selección tras éxito (ya se avisó
            # "Archivo creado correctamente" con el nombre). No mostramos
            # la ruta técnica.
            self.clear_files()
            self.status_text = ""
        elif completed or errored:
            self.status_text = f"Terminado: {completed} completado(s), {errored} con error."
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
            self._show_info(f"No se pudo abrir automáticamente.\nArchivo: {os.path.basename(output_path)}")

    def share_output_file(self, output_path):
        if not output_path or not os.path.isfile(output_path):
            self._show_info("Ese archivo ya no está disponible (¿se movió o se borró?).")
            return
        shared = share_file_external(output_path)
        if not shared:
            self._show_info(f"No se pudo compartir automáticamente.\nArchivo: {os.path.basename(output_path)}")

    # ------------------------------------------------------------- Historial
    def _load_history(self):
        self._apply_history(history.load_history())

    def _add_history(self, name, mode_label, status, path="", size_bytes=None):
        if size_bytes is None and path:
            size_bytes = get_file_size(path)
        updated = history.add_entry(name, mode_label, status, path=path, size_bytes=size_bytes)
        self._apply_history(updated)

    @mainthread
    def _apply_history(self, updated_history):
        from kivy.factory import Factory

        self.history = updated_history
        container = self.root.ids.history_list
        container.clear_widgets()
        for entry in self.history:
            card = Factory.HistoryCard()
            card.entry_id = entry.get("id", "")
            card.name = entry.get("name", "")
            card.mode = entry.get("mode", "")
            card.status = entry.get("status", "")
            card.timestamp = entry.get("timestamp", "")
            card.size_text = format_file_size(entry.get("size_bytes"))
            card.output_path = entry.get("path", "")
            container.add_widget(card)

    def open_history_actions(self, entry_id):
        entry = next((e for e in self.history if e.get("id") == entry_id), None)
        if not entry:
            return

        from kivy.uix.button import Button
        from kivy.uix.boxlayout import BoxLayout as KBox
        from kivy.uix.textinput import TextInput

        content = KBox(orientation="vertical", spacing=10, padding=10)
        popup = Popup(
            title=f"Acciones: {entry.get('name', '')}",
            size_hint=(0.9, 0.5),
            content=content,
        )

        rename_input = TextInput(
            text=os.path.splitext(entry.get("name", ""))[0],
            multiline=False,
            size_hint_y=None,
            height="40dp",
        )
        content.add_widget(rename_input)

        def do_rename(*_a):
            new_name = rename_input.text.strip()
            if not new_name:
                return
            try:
                old_path = entry.get("path", "")
                new_path = rename_file(old_path, new_name)
                history.update_entry(entry_id, path=new_path, name=os.path.basename(new_path))
                self._apply_history(history.load_history())
                popup.dismiss()
            except Exception as exc:
                self._show_info(f"No se pudo renombrar: {exc}")

        rename_btn = Button(text="Renombrar", size_hint_y=None, height="44dp")
        rename_btn.bind(on_release=do_rename)
        content.add_widget(rename_btn)

        def ask_delete(*_a):
            popup.dismiss()
            self._confirm_delete(entry_id, entry.get("name", ""), entry.get("path", ""))

        delete_btn = Button(
            text="Eliminar archivo", size_hint_y=None, height="44dp",
            background_color=(0.8, 0.3, 0.3, 1),
        )
        delete_btn.bind(on_release=ask_delete)
        content.add_widget(delete_btn)

        close_btn = Button(text="Cerrar", size_hint_y=None, height="40dp")
        close_btn.bind(on_release=lambda *_a: popup.dismiss())
        content.add_widget(close_btn)

        popup.open()

    def _confirm_delete(self, entry_id, name, path):
        from kivy.uix.button import Button
        from kivy.uix.boxlayout import BoxLayout as KBox
        from kivy.uix.label import Label

        content = KBox(orientation="vertical", spacing=10, padding=10)
        popup = Popup(title="Confirmar eliminación", size_hint=(0.85, 0.35), content=content)

        content.add_widget(Label(text=f"¿Eliminar '{name}' definitivamente?"))

        buttons = KBox(spacing=10, size_hint_y=None, height="44dp")

        def do_delete(*_a):
            delete_file(path)
            updated = history.remove_entry(entry_id)
            self._apply_history(updated)
            popup.dismiss()

        confirm_btn = Button(text="Eliminar", background_color=(0.8, 0.3, 0.3, 1))
        confirm_btn.bind(on_release=do_delete)
        cancel_btn = Button(text="Cancelar")
        cancel_btn.bind(on_release=lambda *_a: popup.dismiss())

        buttons.add_widget(cancel_btn)
        buttons.add_widget(confirm_btn)
        content.add_widget(buttons)

        popup.open()


if __name__ == "__main__":
    DocConvertApp().run()
