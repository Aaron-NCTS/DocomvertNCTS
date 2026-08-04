"""
Hook de compilación para python-for-android / Buildozer.

Buildozer no tiene una opción directa en buildozer.spec para agregar un
elemento <provider> dentro de <application> del AndroidManifest.xml (la
opción `android.extra_manifest_xml` solo inserta XML ANTES de <application>,
y `android.extra_manifest_application_arguments` solo agrega atributos al
tag <application>, no elementos hijos). Por eso se necesita este hook:
se ejecuta justo antes de que Gradle empaquete el APK, cuando el
AndroidManifest.xml ya fue generado por python-for-android pero el archivo
en disco todavía se puede editar.

Aviso honesto: la ruta exacta del AndroidManifest.xml generado puede variar
entre versiones de python-for-android. Este hook prueba varias rutas
conocidas; si ninguna existe, no falla la compilación -- simplemente no
agrega el FileProvider, y el código de la app (android_utils.py) ya tiene
manejo de respaldo para ese caso (cae a mostrar la ruta del archivo en vez
de abrir/compartir automáticamente).
"""

import os
import re

PROVIDER_AUTHORITY_ATTR = 'mx.novacoretech.docconvertncts.fileprovider'

PROVIDER_XML = """
        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="{package}.fileprovider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data
                android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/file_paths" />
        </provider>
"""

FILE_PATHS_XML = """<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <external-path name="external_files" path="." />
    <external-files-path name="app_external_files" path="." />
    <files-path name="internal_files" path="." />
    <cache-path name="cache_files" path="." />
</paths>
"""


def _find_manifest_path(ctx):
    candidates = [
        os.path.join(ctx.dist_dir, "src", "main", "AndroidManifest.xml"),
        os.path.join(ctx.dist_dir, "AndroidManifest.xml"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _find_res_xml_dir(ctx):
    candidates = [
        os.path.join(ctx.dist_dir, "src", "main", "res", "xml"),
        os.path.join(ctx.dist_dir, "res", "xml"),
    ]
    for path in candidates:
        if os.path.isdir(os.path.dirname(path)):
            return path
    # Si no existe ninguna carpeta "res" esperada, usar la primera opción
    # de todos modos (se crea si hace falta).
    return candidates[0]


def before_apk_assemble(toolchain):
    try:
        ctx = toolchain.ctx
        manifest_path = _find_manifest_path(ctx)
        if not manifest_path:
            print("[hook fileprovider] No se encontró AndroidManifest.xml; se omite.")
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_content = f.read()

        if "FileProvider" in manifest_content:
            print("[hook fileprovider] Ya existe un FileProvider en el manifest; se omite.")
            return

        package_match = re.search(r'package="([^"]+)"', manifest_content)
        package_name = package_match.group(1) if package_match else "mx.novacoretech.docconvertncts"

        provider_xml = PROVIDER_XML.format(package=package_name)

        # Insertar justo antes del cierre de </application>.
        if "</application>" not in manifest_content:
            print("[hook fileprovider] No se encontró </application>; se omite.")
            return

        new_content = manifest_content.replace(
            "</application>", provider_xml + "\n    </application>"
        )

        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        res_xml_dir = _find_res_xml_dir(ctx)
        os.makedirs(res_xml_dir, exist_ok=True)
        with open(os.path.join(res_xml_dir, "file_paths.xml"), "w", encoding="utf-8") as f:
            f.write(FILE_PATHS_XML)

        print(f"[hook fileprovider] FileProvider agregado correctamente "
              f"(authority: {package_name}.fileprovider).")
    except Exception as exc:
        # Nunca queremos que este hook tumbe la compilación completa por un
        # detalle de FileProvider -- en el peor caso, abrir/compartir cae a
        # su respaldo (mostrar la ruta del archivo).
        print(f"[hook fileprovider] Error no crítico, se omite: {exc}")
