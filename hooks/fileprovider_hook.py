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


def _find_manifest_path(dist_dir):
    candidates = [
        os.path.join(dist_dir, "src", "main", "AndroidManifest.xml"),
        os.path.join(dist_dir, "AndroidManifest.xml"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def before_apk_assemble(toolchain):
    try:
        # IMPORTANTE: dentro de _build_package() (el método que python-for-
        # android usa justo antes de ensamblar el APK, que es donde este
        # hook se ejecuta), la carpeta de la distribución se guarda en
        # `toolchain._dist.dist_dir`, NO en `toolchain.ctx.dist_dir` (son
        # conceptos distintos en esta versión de p4a: ctx.dist_dir es otra
        # ruta base). Usar la variable equivocada hace que el hook nunca
        # encuentre el manifest y no aplique el cambio, en silencio.
        dist_dir = None
        for candidate_attr in ("_dist", "dist"):
            dist_obj = getattr(toolchain, candidate_attr, None)
            if dist_obj is not None and getattr(dist_obj, "dist_dir", None):
                dist_dir = dist_obj.dist_dir
                break
        if not dist_dir:
            dist_dir = getattr(toolchain.ctx, "dist_dir", None)

        if not dist_dir or not os.path.isdir(dist_dir):
            print(f"[hook fileprovider] No se encontró dist_dir válido ({dist_dir}); se omite.")
            return

        manifest_path = _find_manifest_path(dist_dir)
        if not manifest_path:
            print(f"[hook fileprovider] No se encontró AndroidManifest.xml en {dist_dir}; se omite.")
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_content = f.read()

        if "FileProvider" in manifest_content:
            print("[hook fileprovider] Ya existe un FileProvider en el manifest; se omite.")
            return

        package_match = re.search(r'package="([^"]+)"', manifest_content)
        package_name = package_match.group(1) if package_match else "mx.novacoretech.docconvertncts"

        provider_xml = PROVIDER_XML.format(package=package_name)

        if "</application>" not in manifest_content:
            print("[hook fileprovider] No se encontró </application>; se omite.")
            return

        new_content = manifest_content.replace(
            "</application>", provider_xml + "\n    </application>"
        )

        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # El build.py de p4a copia el manifest de src/main/AndroidManifest.xml
        # también a la raíz del dist_dir (para compatibilidad con "ant");
        # si existe esa copia, la actualizamos igual para que ambas coincidan.
        root_copy = os.path.join(dist_dir, "AndroidManifest.xml")
        if os.path.isfile(root_copy) and os.path.abspath(root_copy) != os.path.abspath(manifest_path):
            with open(root_copy, "w", encoding="utf-8") as f:
                f.write(new_content)

        res_xml_dir = os.path.join(os.path.dirname(manifest_path), "res", "xml")
        os.makedirs(res_xml_dir, exist_ok=True)
        with open(os.path.join(res_xml_dir, "file_paths.xml"), "w", encoding="utf-8") as f:
            f.write(FILE_PATHS_XML)

        print(f"[hook fileprovider] FileProvider agregado correctamente en {manifest_path} "
              f"(authority: {package_name}.fileprovider).")
    except Exception as exc:
        # Nunca queremos que este hook tumbe la compilación completa por un
        # detalle de FileProvider -- en el peor caso, abrir/compartir cae a
        # su respaldo (mostrar la ruta del archivo).
        print(f"[hook fileprovider] Error no crítico, se omite: {exc}")
