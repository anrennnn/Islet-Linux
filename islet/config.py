"""Configuración del usuario (~/.config/islet/config.json) e inicio automático."""

import json
import os
import shutil
import sys

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "islet")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
AUTOSTART_PATH = os.path.join(os.path.dirname(CONFIG_DIR), "autostart", "islet.desktop")

DEFAULTS = {"monitor": None, "theme": "dark", "first_run_done": False}
THEMES = {"dark": "Oscuro", "light": "Claro", "glass": "Cristal"}


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self, f, indent=2)
        os.replace(tmp, CONFIG_PATH)


def is_installed():
    """True si se ejecuta desde un paquete del sistema o la instalación portable."""
    return __file__.startswith(("/usr/", os.path.expanduser("~/.local/lib/islet")))


def autostart_enabled():
    return os.path.exists(AUTOSTART_PATH)


def set_autostart(enabled):
    if not enabled:
        try:
            os.remove(AUTOSTART_PATH)
        except FileNotFoundError:
            pass
        return
    exe = shutil.which("islet") or f"{sys.executable} -m islet"
    os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
    with open(AUTOSTART_PATH, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Islet\n"
            "Comment=Isla dinámica con controles multimedia\n"
            f"Exec={exe}\n"
            "Icon=islet\n"
            "X-GNOME-Autostart-enabled=true\n"
            "X-GNOME-Autostart-Delay=3\n"
        )
