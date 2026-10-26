#!/usr/bin/python3
# Lanzador de Islet: el código vive en una carpeta propia (no en site-packages) para que el
# mismo paquete funcione con cualquier versión de Python 3 y en cualquier distro.
import os
import sys

LIBDIR = "@LIBDIR@"
if LIBDIR.startswith("@"):  # versión portable: el código está junto a este archivo
    LIBDIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.environ.get("ISLET_LIBDIR", LIBDIR))
from islet.app import main  # noqa: E402

sys.exit(main())
