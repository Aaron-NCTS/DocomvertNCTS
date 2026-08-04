"""
DocConvert NCTS - Móvil
Convierte PDF <-> Word y Fotos -> PDF directamente en tu Android.
100% local, sin internet. Administra los archivos que ya creaste.

Navegación: ScreenManager con 4 pantallas (Inicio + 3 herramientas),
accesibles desde un menú de tres líneas en el encabezado (sin depender de
ningún carácter Unicode -- se dibuja con el canvas de Kivy para evitar el
"cuadro vacío" que aparece en algunos dispositivos Android cuando la fuente
no tiene el glifo correspondiente).
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
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition

import history
from android_filechooser import ON_ANDROID as ANDROID_PICKER_AVAILABLE
from android_filechooser import open_camera_capture, open_document
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
    has_enough_space,
    notify_media_scanner,
    open_file_external,
    rename_file,
    resolve_to_local_path,
    resolve_unique_path,
    sanitize_filename,
    share_file_external,
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
        "screen_title": "PDF a Word",
        "description": "Convierte documentos PDF en archivos Word.",
        "select_label": "Seleccionar PDF",
        "picker_kind": "pdf",
        "out_ext": ".docx",
        "convert_label": "Convertir a Word",
    },
    MODE_WORD_TO_PDF: {
        "label": "Word -> PDF",
        "screen_title": "Word a PDF",
        "description": "Convierte documentos Word en archivos PDF.",
        "select_label": "Seleccionar documento Word",
        "picker_kind": "word",
        "out_ext": ".pdf",
        "convert_label": "Convertir a PDF",
    },
}

# ------------------------------------------------------------------------ KV
KV = """
#:import dp kivy.metrics.dp

<HamburgerIcon@Widget>:
    size_hint: None, None
    size: dp(24), dp(18)
    canvas:
        Color:
            rgba: 1, 1, 1, 1
        Rectangle:
            pos: self.x, self.y + dp(15)
            size: dp(24), dp(3)
        Rectangle:
            pos: self.x, self.y + dp(7.5)
            size: dp(24), dp(3)
        Rectangle:
            pos: self.x, self.y
            size: dp(24), dp(3)

<TopBar@BoxLayout>:
    title: "DocConvert NCTS"
    subtitle: "Convierte y administra tus documentos"
    show_back: False
    orientation: "horizontal"
    size_hint_y: None
    height: dp(60)
    padding: dp(14), dp(8)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: app.header_color
        Rectangle:
            pos: self.pos
            size: self.size

    Button:
        text: "<"
        font_size: "20sp"
        bold: True
        size_hint_x: None
        width: dp(36) if root.show_back else 0
        opacity: 1 if root.show_back else 0
        disabled: not root.show_back
        background_normal: ""
        background_color: 0, 0, 0, 0
        color: 1, 1, 1, 1
        on_release: app.go_home()

    BoxLayout:
        orientation: "vertical"
        Label:
            text: root.title
            font_size: "18sp"
            bold: True
            halign: "left"
            valign: "middle"
            text_size: self.size
            color: 1, 1, 1, 1
        Label:
            text: root.subtitle
            font_size: "11sp"
            halign: "left"
            valign: "middle"
            text_size: self.size
            color: 0.68, 0.72, 0.85, 1

    Button:
        id: menu_button
        size_hint: None, None
        size: dp(44), dp(44)
        background_normal: ""
        background_color: 0, 0, 0, 0
        on_release: app.open_main_menu(self)

        HamburgerIcon:
            center: self.parent.center


<SectionLabel@Label>:
    size_hint_y: None
    height: dp(26)
    font_size: "13sp"
    bold: True
    color: 0.68, 0.70, 0.78, 1
    halign: "left"
    valign: "middle"
    text_size: self.size


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


<SelectedFileCard>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(66)
    padding: dp(12)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: app.card_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

    BoxLayout:
        orientation: "vertical"
        Label:
            text: root.file_name
            color: app.text_primary
            font_size: "13sp"
            bold: True
            halign: "left"
            valign: "middle"
            text_size: self.size
            shorten: True
            shorten_from: "right"
        Label:
            text: root.file_size + "  -  " + root.status_text
            color: root.status_color
            font_size: "11sp"
            halign: "left"
            valign: "middle"
            text_size: self.size

    Button:
        text: "Quitar"
        size_hint_x: None
        width: dp(66)
        font_size: "11sp"
        disabled: app.converting
        background_normal: ""
        background_color: 0.5, 0.18, 0.2, 1
        color: 1, 1, 1, 1
        on_release: root.on_remove()


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


<HomeScreen>:
    name: "home"
    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        TopBar:
            id: top_bar

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: dp(16)
                spacing: dp(12)

                SectionLabel:
                    text: "Mis archivos creados ({})".format(len(app.history)) if app.history else "Mis archivos creados"

                Label:
                    text: "Selecciona una herramienta desde el menú superior."
                    size_hint_y: None
                    height: dp(24)
                    color: app.text_secondary
                    font_size: "12sp"
                    halign: "left"
                    text_size: self.size

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


<DocumentToolScreen>:
    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        TopBar:
            id: top_bar
            show_back: True

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: dp(16)
                spacing: dp(12)

                Label:
                    id: description_label
                    size_hint_y: None
                    height: dp(20)
                    font_size: "12sp"
                    color: app.text_secondary
                    halign: "left"
                    text_size: self.size

                Button:
                    id: select_button
                    size_hint_y: None
                    height: dp(80)
                    font_size: "15sp"
                    bold: True
                    background_normal: ""
                    background_color: app.accent_color
                    color: 1, 1, 1, 1
                    on_release: root.pick_file()

                BoxLayout:
                    id: file_card_container
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(8)

                TextInput:
                    id: filename_input
                    hint_text: "Nombre del resultado (opcional)"
                    size_hint_y: None
                    height: dp(44) if len(root.files) == 1 else 0
                    opacity: 1 if len(root.files) == 1 else 0
                    disabled: app.converting
                    multiline: False
                    font_size: "13sp"
                    padding: dp(10), dp(12)
                    background_normal: ""
                    background_color: app.card_color
                    foreground_color: app.text_primary
                    cursor_color: app.text_primary

                Label:
                    id: status_label
                    text: root.status_text
                    size_hint_y: None
                    height: max(dp(20), self.texture_size[1]) if root.status_text else 0
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

                Button:
                    id: convert_button
                    size_hint_y: None
                    height: dp(56)
                    font_size: "16sp"
                    bold: True
                    disabled: not root.files or app.converting
                    background_normal: ""
                    background_color: app.accent_color if (root.files and not app.converting) else (0.25, 0.27, 0.32, 1)
                    color: 1, 1, 1, 1
                    on_release: root.start_conversion()

                Label:
                    text: "Los documentos complejos pueden presentar cambios de formato respecto al original."
                    size_hint_y: None
                    height: dp(32)
                    font_size: "11sp"
                    color: app.warning_color
                    halign: "left"
                    valign: "top"
                    text_size: self.width, None


<PhotosToolScreen>:
    name: "photos_to_pdf"
    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: app.bg_color
            Rectangle:
                pos: self.pos
                size: self.size

        TopBar:
            id: top_bar
            title: "Fotos a PDF"
            show_back: True

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: dp(16)
                spacing: dp(12)

                BoxLayout:
                    size_hint_y: None
                    height: dp(56)
                    spacing: dp(8)

                    Button:
                        text: "Elegir de galería"
                        font_size: "13sp"
                        bold: True
                        disabled: app.converting
                        background_normal: ""
                        background_color: app.accent_color
                        color: 1, 1, 1, 1
                        on_release: root.pick_images()

                    Button:
                        text: "Tomar foto"
                        font_size: "13sp"
                        bold: True
                        disabled: app.converting
                        background_normal: ""
                        background_color: 0.2, 0.55, 0.4, 1
                        color: 1, 1, 1, 1
                        on_release: root.take_photo_now()

                BoxLayout:
                    id: photo_list
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(8)

                BoxLayout:
                    orientation: "vertical"
                    size_hint_y: None
                    height: dp(96) if root.files else 0
                    opacity: 1 if root.files else 0
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
                            background_color: app.accent_color if root.page_size == "A4" else app.card_color
                            color: 1, 1, 1, 1
                            on_release: root.page_size = "A4"
                        Button:
                            text: "Pagina Carta"
                            font_size: "11sp"
                            disabled: app.converting
                            background_normal: ""
                            background_color: app.accent_color if root.page_size == "Carta" else app.card_color
                            color: 1, 1, 1, 1
                            on_release: root.page_size = "Carta"

                    BoxLayout:
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(6)
                        Button:
                            text: "Calidad Baja"
                            font_size: "11sp"
                            disabled: app.converting
                            background_normal: ""
                            background_color: app.accent_color if root.quality == "Baja" else app.card_color
                            color: 1, 1, 1, 1
                            on_release: root.quality = "Baja"
                        Button:
                            text: "Calidad Media"
                            font_size: "11sp"
                            disabled: app.converting
                            background_normal: ""
                            background_color: app.accent_color if root.quality == "Media" else app.card_color
                            color: 1, 1, 1, 1
                            on_release: root.quality = "Media"
                        Button:
                            text: "Calidad Alta"
                            font_size: "11sp"
                            disabled: app.converting
                            background_normal: ""
                            background_color: app.accent_color if root.quality == "Alta" else app.card_color
                            color: 1, 1, 1, 1
                            on_release: root.quality = "Alta"

                TextInput:
                    id: filename_input
                    hint_text: "Nombre del PDF (opcional)"
                    size_hint_y: None
                    height: dp(44) if root.files else 0
                    opacity: 1 if root.files else 0
                    disabled: app.converting
                    multiline: False
                    font_size: "13sp"
                    padding: dp(10), dp(12)
                    background_normal: ""
                    background_color: app.card_color
                    foreground_color: app.text_primary
                    cursor_color: app.text_primary

                Label:
                    id: status_label
                    text: root.status_text
                    size_hint_y: None
                    height: max(dp(20), self.texture_size[1]) if root.status_text else 0
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

                Button:
                    text: "Crear PDF"
                    size_hint_y: None
                    height: dp(56)
                    font_size: "16sp"
                    bold: True
                    disabled: not root.files or app.converting
                    background_normal: ""
                    background_color: app.accent_color if (root.files and not app.converting) else (0.25, 0.27, 0.32, 1)
                    color: 1, 1, 1, 1
                    on_release: root.start_conversion()
"""


# ------------------------------------------------------------------- Widgets
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


class SelectedFileCard(BoxLayout):
    file_path = StringProperty("")
    file_name = StringProperty("")
    file_size = StringProperty("")
    status_text = StringProperty("Listo para convertir")
    status_color = ListProperty([0.55, 0.57, 0.63, 1])
    owner_screen = None

    def on_remove(self):
        if self.owner_screen:
            self.owner_screen.remove_file(self.file_path)


class PhotoRow(BoxLayout):
    photo_path = StringProperty("")
    file_name = StringProperty("")
    position = NumericProperty(1)
    owner_screen = None

    def on_move_up(self):
        if self.owner_screen:
            self.owner_screen.move_photo(self.photo_path, -1)

    def on_move_down(self):
        if self.owner_screen:
            self.owner_screen.move_photo(self.photo_path, 1)

    def on_rotate(self):
        if self.owner_screen:
            self.owner_screen.rotate_photo(self.photo_path)

    def on_remove(self):
        if self.owner_screen:
            self.owner_screen.remove_file(self.photo_path)


# ------------------------------------------------------------------- Screens
class HomeScreen(Screen):
    def on_pre_enter(self):
        App.get_running_app().refresh_history_widgets(self.ids.history_list)


class BaseToolScreen(Screen):
    """Funciones comunes a las 3 pantallas de herramientas (selección de
    archivos, tamaño máximo, limpieza de temporales, conversión en hilo
    aparte). Las subclases solo definen cómo elegir archivos y qué función
    de conversión usar."""

    files = ListProperty([])
    status_text = StringProperty("")
    page_size = StringProperty("Carta")
    quality = StringProperty("Media")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.display_names = {}
        self.rows = {}
        self.output_dir = None

    def remove_file(self, path):
        if path in self.files:
            self.files.remove(path)
        self.display_names.pop(path, None)
        row = self.rows.pop(path, None)
        if row and row.parent:
            row.parent.remove_widget(row)

    def clear_selection(self):
        for path in list(self.files):
            self.remove_file(path)
        self.status_text = ""

    def _reject_if_too_large(self, path, size):
        if size is not None and size > MAX_FILE_SIZE_BYTES:
            self.status_text = (
                f"El archivo supera el límite de {MAX_FILE_SIZE_MB // 1024} GB: "
                f"{get_display_name(path)}"
            )
            return True
        return False


class DocumentToolScreen(BaseToolScreen):
    mode = StringProperty(MODE_PDF_TO_WORD)

    def configure(self, mode):
        self.mode = mode
        info = MODE_INFO[mode]
        self.ids.top_bar.title = info["screen_title"]
        self.ids.description_label.text = info["description"]
        self.ids.select_button.text = info["select_label"]
        self.ids.convert_button.text = info["convert_label"]

    def pick_file(self):
        info = MODE_INFO[self.mode]
        kind = info["picker_kind"]

        if ANDROID_PICKER_AVAILABLE:
            open_document(kind, multiple=True, on_selection=self._on_files_selected)
        else:
            try:
                from plyer import filechooser

                desktop_filters = {
                    "pdf": [("Documentos PDF", "*.pdf")],
                    "word": [("Documentos Word", "*.doc;*.docx")],
                }
                filechooser.open_file(
                    on_selection=self._on_files_selected,
                    multiple=True,
                    filters=desktop_filters.get(kind),
                )
            except Exception as exc:
                self.status_text = f"No se pudo abrir el selector de archivos: {exc}"

    def _on_files_selected(self, selection):
        if not selection:
            return
        for path in selection:
            if path in self.files:
                continue
            size = get_file_size(path)
            if self._reject_if_too_large(path, size):
                continue
            self.files.append(path)
            self.display_names[path] = get_display_name(path)
            self._add_card(path, size)

    def _add_card(self, path, size):
        from kivy.factory import Factory

        card = Factory.SelectedFileCard()
        card.owner_screen = self
        card.file_path = path
        card.file_name = self.display_names.get(path, Path(path).name)
        card.file_size = format_file_size(size if size is not None else get_file_size(path))
        self.rows[path] = card
        self.ids.file_card_container.add_widget(card)

    def start_conversion(self):
        app = App.get_running_app()
        if not self.files or app.converting:
            return
        app.start_document_conversion(self)


class PhotosToolScreen(BaseToolScreen):
    def pick_images(self):
        if ANDROID_PICKER_AVAILABLE:
            open_document("images", multiple=True, on_selection=self._on_files_selected)
        else:
            try:
                from plyer import filechooser

                filechooser.open_file(
                    on_selection=self._on_files_selected,
                    multiple=True,
                    filters=[("Imágenes", "*.jpg;*.jpeg;*.png;*.webp")],
                )
            except Exception as exc:
                self.status_text = f"No se pudo abrir el selector de imágenes: {exc}"

    def take_photo_now(self):
        def _after_permission(granted):
            if not granted:
                self.status_text = "Sin permiso de cámara: no se puede tomar la foto."
                return
            if ANDROID_PICKER_AVAILABLE:
                started = open_camera_capture(self._on_photo_taken, temp_cache_dir())
            else:
                started = False
            if not started:
                self.status_text = "La cámara no está disponible en este dispositivo/entorno."

        ensure_camera_permission(_after_permission)

    def _on_photo_taken(self, photo_path):
        if photo_path:
            self._on_files_selected([photo_path])

    def _on_files_selected(self, selection):
        if not selection:
            return
        added = 0
        rejected_messages = []
        for path in selection:
            if path in self.files:
                continue  # evita duplicados si el usuario vuelve a elegir la misma foto
            size = get_file_size(path)
            if self._reject_if_too_large(path, size):
                continue

            try:
                local_path = resolve_to_local_path(path, temp_cache_dir())
            except Exception as exc:
                rejected_messages.append(
                    f"{get_display_name(path)}: no se pudo acceder a la imagen ({exc})."
                )
                continue

            try:
                from image_converter import validate_image_file

                validate_image_file(local_path)
            except Exception as exc:
                rejected_messages.append(f"{get_display_name(path)}: {exc}")
                cleanup_temp_file(local_path, temp_cache_dir())
                continue

            self.files.append(path)
            self.display_names[path] = get_display_name(path) or Path(local_path).name
            self._add_photo_row(path, local_path)
            added += 1

        if rejected_messages:
            self.status_text = " | ".join(rejected_messages)
        elif added:
            self.status_text = f"{added} foto(s) agregada(s)."

    def _add_photo_row(self, path, local_path):
        from kivy.factory import Factory

        row = Factory.PhotoRow()
        row.owner_screen = self
        row.photo_path = local_path
        row.file_name = self.display_names.get(path, Path(local_path).name)
        row.position = len(self.files)
        self.rows[path] = row
        self.ids.photo_list.add_widget(row)
        if not hasattr(self, "_local_paths"):
            self._local_paths = {}
        self._local_paths[path] = local_path

    def _refresh_positions(self):
        for index, path in enumerate(self.files):
            row = self.rows.get(path)
            if row:
                row.position = index + 1

    def move_photo(self, path, direction):
        app = App.get_running_app()
        if app.converting or path not in self.files:
            return
        index = self.files.index(path)
        new_index = index + direction
        if new_index < 0 or new_index >= len(self.files):
            return
        self.files[index], self.files[new_index] = self.files[new_index], self.files[index]

        container = self.ids.photo_list
        row = self.rows.get(path)
        if row:
            container.remove_widget(row)
            container.add_widget(row, index=len(container.children) - new_index)
        self._refresh_positions()

    def rotate_photo(self, path):
        app = App.get_running_app()
        if app.converting:
            return
        local_path = getattr(self, "_local_paths", {}).get(path, path)
        try:
            rotate_image_file(local_path, 90)
        except Exception as exc:
            app.show_info(f"No se pudo rotar la foto: {exc}")
            return

        from kivy.cache import Cache

        Cache.remove("kv.image")
        Cache.remove("kv.texture")
        row = self.rows.get(path)
        if row:
            row.photo_path = ""
            row.photo_path = local_path

    def remove_file(self, path):
        super().remove_file(path)
        if hasattr(self, "_local_paths"):
            self._local_paths.pop(path, None)
        self._refresh_positions()

    def start_conversion(self):
        app = App.get_running_app()
        if not self.files or app.converting:
            return
        app.start_photos_conversion(self)


# ----------------------------------------------------------------------- App
class DocConvertApp(App):
    converting = BooleanProperty(False)
    cancel_requested = BooleanProperty(False)
    history = ListProperty([])

    bg_color = ListProperty(list(BG))
    header_color = ListProperty(list(HEADER))
    card_color = ListProperty(list(CARD))
    accent_color = ListProperty(list(ACCENT))
    warning_color = ListProperty(list(WARNING))
    text_primary = ListProperty(list(TEXT_PRIMARY))
    text_secondary = ListProperty(list(TEXT_SECONDARY))
    text_muted = ListProperty(list(TEXT_MUTED))

    def build(self):
        Builder.load_string(KV)
        self.output_dir = None

        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.home_screen = HomeScreen(name="home")

        self.pdf_screen = DocumentToolScreen(name="pdf_to_word")
        self.pdf_screen.configure(MODE_PDF_TO_WORD)

        self.word_screen = DocumentToolScreen(name="word_to_pdf")
        self.word_screen.configure(MODE_WORD_TO_PDF)

        self.photos_screen = PhotosToolScreen(name="photos_to_pdf")

        self.sm.add_widget(self.home_screen)
        self.sm.add_widget(self.pdf_screen)
        self.sm.add_widget(self.word_screen)
        self.sm.add_widget(self.photos_screen)

        return self.sm

    def on_start(self):
        ensure_permissions(self._on_permissions_result)
        Window.bind(on_keyboard=self._on_keyboard)
        self._load_history()

    def _on_keyboard(self, window, key, *args):
        if key == 27:  # botón físico "atrás" de Android
            if self.converting:
                self._toast("Espera a que termine (o cancela) antes de salir.")
                return True
            if self.sm.current != "home":
                self.go_home()
                return True
        return False

    def go_home(self):
        if self.converting:
            return
        self.sm.current = "home"

    def go_to_screen(self, screen_name):
        self.sm.current = screen_name

    def _on_permissions_result(self, granted: bool):
        self.output_dir = default_output_dir()
        if not granted:
            self._toast("Sin permisos: no se podrán guardar los archivos convertidos.")

    def _toast(self, message):
        current = self.sm.current_screen
        if hasattr(current, "status_text"):
            current.status_text = message

    # ------------------------------------------------------------ Menú
    def open_main_menu(self, anchor_widget):
        from kivy.uix.button import Button
        from kivy.uix.dropdown import DropDown

        dropdown = DropDown(auto_width=False, width=Window.width * 0.65)

        def item(text, screen_name):
            btn = Button(
                text=text,
                size_hint_y=None,
                height="48dp",
                background_normal="",
                background_color=self.card_color,
                color=self.text_primary,
            )
            btn.bind(
                on_release=lambda *_: (dropdown.dismiss(), self.go_to_screen(screen_name))
            )
            dropdown.add_widget(btn)

        item("PDF a Word", "pdf_to_word")
        item("Word a PDF", "word_to_pdf")
        item("Fotos a PDF", "photos_to_pdf")

        dropdown.open(anchor_widget)

    # ------------------------------------------------------- Conversión
    def cancel_conversion(self):
        if self.converting:
            self.cancel_requested = True
            self._toast("Cancelando... se detendrá después del archivo actual.")

    def start_document_conversion(self, screen):
        self.converting = True
        self.cancel_requested = False
        screen.status_text = "Iniciando conversión..."
        thread = threading.Thread(
            target=self._document_worker, args=(screen,), daemon=True
        )
        thread.start()

    def _document_worker(self, screen):
        completed = 0
        errored = 0
        output_dir = ""
        cache_dir = temp_cache_dir()
        mode = screen.mode
        out_ext = MODE_INFO[mode]["out_ext"]
        mode_label = MODE_INFO[mode]["label"]
        custom_name = ""
        try:
            custom_name = screen.ids.filename_input.text.strip()
        except Exception:
            pass

        try:
            output_dir = self.output_dir or default_output_dir()

            for path in list(screen.files):
                if self.cancel_requested:
                    self._update_card_status(screen, path, "Cancelado", (0.6, 0.6, 0.35, 1))
                    continue

                display_name = screen.display_names.get(path, Path(path).name)
                local_path = None
                temp_output_path = None
                try:
                    if len(screen.files) == 1 and custom_name:
                        base_name = sanitize_filename(custom_name)
                    else:
                        base_name = sanitize_filename(Path(display_name).stem or "documento")
                    final_name = base_name + out_ext
                    final_output_path = resolve_unique_path(output_dir, final_name)
                    temp_output_path = final_output_path + ".part"

                    if not has_enough_space(output_dir, get_file_size(path) or 0):
                        raise ConversionError("No hay suficiente espacio disponible.")

                    self._update_card_status(
                        screen, path, "Convirtiendo...", (0.35, 0.55, 0.95, 1)
                    )
                    self._set_screen_status(screen, f"Convirtiendo: {display_name}")

                    local_path = resolve_to_local_path(path, cache_dir)

                    def progress_cb(msg, p=display_name):
                        self._set_screen_status(screen, f"{p}: {msg}")

                    if mode == MODE_PDF_TO_WORD:
                        convert_pdf_to_word(local_path, temp_output_path, progress_cb=progress_cb)
                    else:
                        convert_word_to_pdf(local_path, temp_output_path, progress_cb=progress_cb)

                    os.replace(temp_output_path, final_output_path)
                    notify_media_scanner(final_output_path)
                    self._update_card_status(
                        screen, path, "Completado", (0.3, 0.75, 0.5, 1)
                    )
                    self._add_history(
                        os.path.basename(final_output_path), mode_label, "Completado",
                        final_output_path,
                    )
                    self._notify_success(os.path.basename(final_output_path))
                    completed += 1
                except ConversionError as exc:
                    self._update_card_status(screen, path, "Error", (0.9, 0.35, 0.38, 1))
                    self._show_error_popup(display_name, str(exc))
                    errored += 1
                except Exception as exc:
                    # Registro de depuración (consola/logcat, nunca al usuario
                    # como traceback completo): permite diagnosticar fallos
                    # reales sin adivinar. El usuario ve un mensaje corto con
                    # el tipo de error, no el traceback completo.
                    import traceback

                    print(f"[DocConvertNCTS] Error convirtiendo '{display_name}' "
                          f"(modo={mode}, path={path}):")
                    traceback.print_exc()

                    self._update_card_status(screen, path, "Error", (0.9, 0.35, 0.38, 1))
                    self._show_error_popup(
                        display_name,
                        f"No se pudo procesar el archivo ({type(exc).__name__}: {exc}). "
                        f"Vuelve a seleccionarlo desde Descargas o Documentos.",
                    )
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
            import traceback

            print(f"[DocConvertNCTS] Error inesperado en _document_worker:")
            traceback.print_exc()
            self._set_screen_status(screen, f"Error inesperado durante la conversión: {exc}")
        finally:
            self._finish_document(screen, completed, errored)

    def start_photos_conversion(self, screen):
        self.converting = True
        self.cancel_requested = False
        screen.status_text = "Iniciando conversión..."
        thread = threading.Thread(
            target=self._photos_worker, args=(screen,), daemon=True
        )
        thread.start()

    def _photos_worker(self, screen):
        output_dir = ""
        try:
            output_dir = self.output_dir or default_output_dir()
            custom_name = ""
            try:
                custom_name = screen.ids.filename_input.text.strip()
            except Exception:
                pass

            raw_name = sanitize_filename(custom_name or "Fotos a PDF")
            if not raw_name.lower().endswith(".pdf"):
                raw_name += ".pdf"
            final_output_path = resolve_unique_path(output_dir, raw_name)
            temp_output_path = final_output_path + ".part"

            local_paths = [
                getattr(screen, "_local_paths", {}).get(p, p) for p in list(screen.files)
            ]

            estimated_size = sum((get_file_size(p) or 0) for p in local_paths)
            if not has_enough_space(output_dir, estimated_size):
                raise ConversionError("No hay suficiente espacio disponible.")

            def progress_cb(msg):
                self._set_screen_status(screen, msg)

            convert_images_to_pdf(
                local_paths,
                temp_output_path,
                page_size=screen.page_size,
                quality=screen.quality,
                progress_cb=progress_cb,
            )

            os.replace(temp_output_path, final_output_path)
            notify_media_scanner(final_output_path)
            self._add_history(
                os.path.basename(final_output_path), "Fotos -> PDF", "Completado",
                final_output_path,
            )
            self._notify_success(os.path.basename(final_output_path))
            self._finish_photos(screen, success=True)
        except ConversionError as exc:
            self._show_error_popup("Fotos a PDF", str(exc))
            self._finish_photos(screen, success=False)
        except Exception as exc:
            import traceback

            print("[DocConvertNCTS] Error inesperado en _photos_worker:")
            traceback.print_exc()

            self._show_error_popup(
                "Fotos a PDF",
                f"No se pudo crear el PDF ({type(exc).__name__}: {exc}). "
                f"Intenta quitar la última foto agregada y vuelve a intentar.",
            )
            self._finish_photos(screen, success=False)

    @mainthread
    def _update_card_status(self, screen, path, text, color):
        row = screen.rows.get(path)
        if row and hasattr(row, "status_text"):
            row.status_text = text
            row.status_color = list(color)

    @mainthread
    def _set_screen_status(self, screen, text):
        screen.status_text = text

    @mainthread
    def _notify_success(self, filename):
        self.show_info(f"Archivo creado correctamente\n\n{filename}")

    @mainthread
    def _finish_document(self, screen, completed, errored):
        self.converting = False
        self.cancel_requested = False
        if completed or errored:
            screen.status_text = f"Terminado: {completed} completado(s), {errored} con error."
        else:
            screen.status_text = "Conversión cancelada."
        if completed:
            screen.clear_selection()
            try:
                screen.ids.filename_input.text = ""
            except Exception:
                pass

    @mainthread
    def _finish_photos(self, screen, success):
        self.converting = False
        self.cancel_requested = False
        if success:
            screen.clear_selection()
            try:
                screen.ids.filename_input.text = ""
            except Exception:
                pass
            screen.status_text = ""
        else:
            screen.status_text = "No se pudo crear el PDF."

    @mainthread
    def _show_error_popup(self, filename, message):
        from kivy.uix.label import Label

        popup = Popup(title=f"Error: {filename}", size_hint=(0.85, 0.35))
        popup.content = Label(text=message, text_size=(Window.width * 0.7, None))
        popup.open()

    @mainthread
    def show_info(self, message):
        from kivy.uix.label import Label

        popup = Popup(title="DocConvert NCTS", size_hint=(0.85, 0.35))
        popup.content = Label(text=message, text_size=(Window.width * 0.7, None))
        popup.open()

    # ---------------------------------------------------------- Abrir/compartir
    def open_output_file(self, output_path):
        if not output_path or not os.path.isfile(output_path):
            self.show_info("Ese archivo ya no está disponible (¿se movió o se borró?).")
            return
        if not open_file_external(output_path):
            self.show_info(f"No se pudo abrir automáticamente.\n{os.path.basename(output_path)}")

    def share_output_file(self, output_path):
        if not output_path or not os.path.isfile(output_path):
            self.show_info("Ese archivo ya no está disponible (¿se movió o se borró?).")
            return
        if not share_file_external(output_path):
            self.show_info(f"No se pudo compartir automáticamente.\n{os.path.basename(output_path)}")

    # ------------------------------------------------------------- Historial
    def _load_history(self):
        self.history = history.load_history()

    def _add_history(self, name, mode_label, status, path="", size_bytes=None):
        if size_bytes is None and path:
            size_bytes = get_file_size(path)
        # IMPORTANTE: history.add_entry() solo hace I/O de archivo (seguro
        # en el hilo de fondo). Pero asignar self.history (una ListProperty
        # de Kivy) SIEMPRE debe pasar por el hilo principal -- hacerlo
        # directamente desde el hilo de conversión puede lanzar una
        # excepción interna de Kivy que, si esta función se llama dentro
        # del try/except de la conversión, se confunde con un error de la
        # propia conversión (aunque el archivo se haya creado bien).
        updated = history.add_entry(name, mode_label, status, path=path, size_bytes=size_bytes)
        self._apply_history(updated)

    @mainthread
    def _apply_history(self, updated_history):
        self.history = updated_history
        if self.sm.current == "home":
            self.refresh_history_widgets(self.home_screen.ids.history_list)

    @mainthread
    def refresh_history_widgets(self, container):
        from kivy.factory import Factory

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

        from kivy.uix.boxlayout import BoxLayout as KBox
        from kivy.uix.button import Button
        from kivy.uix.textinput import TextInput

        content = KBox(orientation="vertical", spacing=10, padding=10)
        popup = Popup(
            title=f"Acciones: {entry.get('name', '')}", size_hint=(0.9, 0.5), content=content
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
                new_path = rename_file(entry.get("path", ""), new_name)
                history.update_entry(entry_id, path=new_path, name=os.path.basename(new_path))
                self.history = history.load_history()
                if self.sm.current == "home":
                    self.refresh_history_widgets(self.home_screen.ids.history_list)
                popup.dismiss()
            except Exception as exc:
                self.show_info(f"No se pudo renombrar: {exc}")

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
        from kivy.uix.boxlayout import BoxLayout as KBox
        from kivy.uix.button import Button
        from kivy.uix.label import Label

        content = KBox(orientation="vertical", spacing=10, padding=10)
        popup = Popup(title="Confirmar eliminación", size_hint=(0.85, 0.35), content=content)
        content.add_widget(Label(text=f"¿Eliminar '{name}' definitivamente?"))

        buttons = KBox(spacing=10, size_hint_y=None, height="44dp")

        def do_delete(*_a):
            delete_file(path)
            self.history = history.remove_entry(entry_id)
            if self.sm.current == "home":
                self.refresh_history_widgets(self.home_screen.ids.history_list)
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
