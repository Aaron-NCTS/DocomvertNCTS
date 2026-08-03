"""
Receta LOCAL de lxml para python-for-android.

Por qué existe este archivo: la receta oficial de python-for-android para
lxml está fijada a la versión 4.8.0 (2022), cuyo código C generado por
Cython accede directamente a campos internos de `struct _frame` de CPython.
Python 3.11 cambió esa estructura interna (la volvió opaca), así que ese
código C ya no compila ("incomplete definition of type 'struct _frame'").

Esta receta local (en `recipes/lxml/`, referenciada desde `buildozer.spec`
vía `p4a.local_recipes = ./recipes`) tiene prioridad sobre la oficial y
apunta a una versión moderna de lxml (5.2.2) cuyo código C ya fue
regenerado con una versión de Cython compatible con Python 3.11+.

El resto de la lógica (compilación estática contra libxml2/libxslt) se
mantiene igual que la receta oficial, ya que esas variables de entorno son
una convención estable del propio setup.py de lxml a través de sus
versiones.
"""

from os import uname
from os.path import exists, join

from pythonforandroid.recipe import CompiledComponentsPythonRecipe, Recipe


class LXMLRecipe(CompiledComponentsPythonRecipe):
    version = '5.2.2'
    url = 'https://files.pythonhosted.org/packages/source/l/lxml/lxml-{version}.tar.gz'
    depends = ['librt', 'libxml2', 'libxslt', 'setuptools']
    name = 'lxml'

    call_hostpython_via_targetpython = False  # Debido a setuptools

    def should_build(self, arch):
        super().should_build(arch)

        py_ver = self.ctx.python_recipe.major_minor_version_string
        build_platform = "{system}-{machine}".format(
            system=uname()[0], machine=uname()[-1]
        ).lower()
        build_dir = join(
            self.get_build_dir(arch.arch),
            "build",
            "lib." + build_platform + "-" + py_ver,
            "lxml",
        )
        py_libs = ["_elementpath.so", "builder.so", "etree.so", "objectify.so"]

        return not all([exists(join(build_dir, lib)) for lib in py_libs])

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)

        libxslt_recipe = Recipe.get_recipe('libxslt', self.ctx)
        libxslt_build_dir = libxslt_recipe.get_build_dir(arch.arch)

        libxml2_recipe = Recipe.get_recipe('libxml2', self.ctx)
        libxml2_build_dir = libxml2_recipe.get_build_dir(arch.arch)

        # lxml 5.x renombró la variable de entorno de "STATIC" a
        # "STATICBUILD" (ver setupinfo.py de lxml); el resto de las
        # variables (WITH_XML2_CONFIG, WITH_XSLT_CONFIG, LXML_STATIC_*)
        # se mantienen igual entre versiones.
        env["STATICBUILD"] = "true"

        env["LXML_STATIC_INCLUDE_DIRS"] = "{}:{}".format(
            join(libxml2_build_dir, "include"), join(libxslt_build_dir)
        )
        env["LXML_STATIC_LIBRARY_DIRS"] = "{}:{}:{}".format(
            join(libxml2_build_dir, ".libs"),
            join(libxslt_build_dir, "libxslt", ".libs"),
            join(libxslt_build_dir, "libexslt", ".libs"),
        )

        env["WITH_XML2_CONFIG"] = join(libxml2_build_dir, "xml2-config")
        env["WITH_XSLT_CONFIG"] = join(libxslt_build_dir, "xslt-config")

        env["LXML_STATIC_BINARIES"] = "{}:{}:{}".format(
            join(libxml2_build_dir, ".libs", "libxml2.a"),
            join(libxslt_build_dir, "libxslt", ".libs", "libxslt.a"),
            join(libxslt_build_dir, "libexslt", ".libs", "libexslt.a"),
        )

        return env


recipe = LXMLRecipe()
