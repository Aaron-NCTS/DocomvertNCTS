# DocConvert NCTS - Móvil (Android)

Versión Android de DocConvert NCTS. **Solo incluye PDF → Word** (con texto
seleccionable; sin OCR). La conversión Word → PDF se queda en la versión de
escritorio, ya que depende de Microsoft Word/LibreOffice, que no existen en
Android.

Todo el procesamiento ocurre en el propio dispositivo: no se sube ningún
archivo a internet.

## Motor de conversión: pypdf (no pdf2docx ni pdfminer.six)

La versión de escritorio usa `pdf2docx` (que depende de `pymupdf`/PyMuPDF).
**Esa combinación no compila para Android**: PyMuPDF es una librería en C
sin "receta" de compilación cruzada en python-for-android. Se intentó
también `pdfminer.six`, pero depende de `cryptography` (extensión nativa en
Rust/C sin build para Android), así que tampoco compila.

La versión móvil usa **`pypdf` + `python-docx`**, ambos sin ninguna
dependencia nativa obligatoria — la única combinación que realmente compila
en este entorno. Trade-off que debes conocer: `pypdf` entrega el texto
línea por línea (no por bloques/párrafos), así que los párrafos se
reconstruyen con una heurística de puntuación (una línea que termina en
`. ! ? : ;` se asume que cierra un párrafo). Esto funciona bien para texto
corrido (cartas, reportes, contratos), pero:
- No reconstruye tablas como tablas (el contenido de cada celda aparece
  como texto suelto, en orden de lectura).
- Títulos/encabezados sin punto final pueden quedar unidos al párrafo
  siguiente en vez de separados.

## 1. Probar en tu PC antes de compilar (recomendado)

```bash
pip install -r requirements.txt
python main.py
```

Se abrirá una ventana de escritorio con la misma interfaz que verás en el
celular. Prueba seleccionar un PDF y convertirlo antes de generar el APK —
así ahorras tiempo si algo necesita ajuste.

## 2. Compilar el APK

Tienes dos caminos: **GitHub Actions (recomendado si no tienes WSL)** o **Buildozer local en Linux/WSL**.

### 2.A Compilar en la nube con GitHub Actions (no necesitas WSL)

El proyecto ya incluye `.github/workflows/build-apk.yml`, que compila el APK
automáticamente en los servidores de GitHub cada vez que subes cambios.

**Paso 1 — Sube el proyecto a GitHub** (desde PowerShell, dentro de la carpeta
`DocConvertMobile`):

```powershell
cd C:\Users\nytan\Downloads\DocConvertMobile
git init
git add .
git commit -m "Primera versión de DocConvert NCTS móvil"
git branch -M main
```

Crea un repo vacío en https://github.com/new (por ejemplo `DocConvertMobile`,
puede ser privado), luego:

```powershell
git remote add origin https://github.com/TU-USUARIO/DocConvertMobile.git
git push -u origin main
```

**Paso 2 — Ver la compilación:**

1. Entra a tu repo en GitHub → pestaña **Actions**.
2. Verás el workflow "Build APK" corriendo (tarda 15-30 min la primera vez).
3. Cuando termine en verde, entra a esa ejecución y baja hasta **Artifacts**.
4. Descarga `DocConvertNCTS-apk` — es un `.zip` que contiene el `.apk` dentro.

**Paso 3 — Instalar en tu celular:** copia el `.apk` a tu teléfono (por USB,
Drive, WhatsApp a ti mismo, etc.) y ábrelo. Android pedirá permitir
"instalar apps de fuentes desconocidas" la primera vez.

Cada vez que quieras una nueva versión: haz cambios, `git add .`,
`git commit`, `git push`, y espera a que Actions termine.

### 2.B Compilar localmente con Buildozer (Linux o WSL)

Buildozer **solo corre en Linux** (o WSL2 en Windows).


### 2.1 Instalar Buildozer y dependencias del sistema

```bash
sudo apt update
sudo apt install -y python3-pip build-essential git python3-dev \
    ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev \
    zlib1g-dev openjdk-17-jdk unzip

pip install --user buildozer cython
```

### 2.2 Compilar (primera vez tarda 20-40 min: descarga Android SDK/NDK)

Desde la carpeta del proyecto (donde está `buildozer.spec`):

```bash
buildozer android debug
```

El APK queda en `bin/docconvertncts-1.0.0-arm64-v8a_armeabi-v7a-debug.apk`.

### 2.3 Instalar en tu celular

Con el celular conectado por USB y depuración USB activada:

```bash
buildozer android deploy run logcat
```

O simplemente copia el `.apk` al celular y ábrelo (Android pedirá permitir
"instalar apps de fuentes desconocidas" la primera vez).

## 3. Notas importantes

- **Primera compilación**: Buildozer descarga el Android SDK/NDK completo
  (varios GB). Necesitas buena conexión e internet libre en esos dominios.
- **PyMuPDF (`fitz`) en Android**: la mayoría de las veces compila bien con
  Buildozer moderno, pero si el build falla en ese paquete específico,
  avísame el error exacto y lo resolvemos (a veces requiere fijar una
  versión distinta de PyMuPDF).
- **Permisos de almacenamiento**: en el primer arranque la app pedirá
  permiso de almacenamiento. Si el usuario lo niega, no podrá guardar los
  archivos convertidos (se le avisa en pantalla).
- **`android.api = 32`**: se fijó así a propósito para evitar la complejidad
  del "scoped storage" de Android 13+. Si más adelante quieres soportar
  versiones más nuevas con guardado más robusto, hay que migrar el guardado
  a `MediaStore`/`SAF` — es un cambio bien delimitado, avísame cuando quieras
  hacerlo.
- **Reconstruir tras cambios de código**: `buildozer android debug` de nuevo
  es suficiente (no vuelve a descargar el SDK/NDK).

## 4. Estructura del proyecto

```
DocConvertMobile/
├── main.py            # App Kivy (interfaz + flujo de conversión)
├── converter.py        # Lógica de conversión PDF->Word (pdf2docx)
├── android_utils.py    # Permisos y rutas de almacenamiento específicas de Android
├── buildozer.spec       # Configuración de compilación Android
├── requirements.txt     # Dependencias para probar en escritorio
└── assets/
    └── icon.png          # Ícono de la app
```
