"""Arranque: entorno gráfico, instancia única, menú y bandeja."""

import os
import signal
import sys


def _prefer_x11():
    # En Wayland una ventana normal no puede elegir su posición ni quedar siempre encima,
    # así que usamos XWayland cuando existe. GDK_BACKEND=wayland lo desactiva.
    wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY")
    if wayland and os.environ.get("DISPLAY") and "GDK_BACKEND" not in os.environ:
        os.environ["GDK_BACKEND"] = "x11"


_prefer_x11()

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from islet import __version__  # noqa: E402
from islet import config as cfg  # noqa: E402
from islet.island import IslandWindow  # noqa: E402
from islet.mpris import MprisWatcher  # noqa: E402

APP_ID = "io.github.anrennnn.islet"


def _load_indicator():
    """AppIndicator (StatusNotifier) si está instalado; si no, Gtk.StatusIcon (bandeja XEmbed)."""
    for name in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(name, "0.1")
            return __import__("gi.repository", fromlist=[name]).__dict__[name]
        except (ValueError, ImportError, KeyError):
            continue
    return None


class IsletApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config = cfg.Config()
        self.window = None
        self.watcher = None
        self.state = {"active": None, "players": []}
        self.indicator = None
        self.status_icon = None
        self._last_logged = None
        self._players_key = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        GLib.set_application_name("Islet")
        # Primera vez que se abre la versión instalada: inicio automático activado
        # (se quita desde el menú de la isla o de la bandeja).
        if not self.config.get("first_run_done"):
            if cfg.is_installed():
                try:
                    cfg.set_autostart(True)
                except OSError as err:
                    print(f"[islet] autoarranque: {err}", flush=True)
            self.config["first_run_done"] = True
            self.config.save()

        self.window = IslandWindow(self, self.config, self.command, self.popup_menu)
        self.watcher = MprisWatcher(self.on_media)
        try:
            self.watcher.start()
        except GLib.Error as err:
            print(f"[mpris] sin bus de sesión D-Bus: {err.message}", flush=True)
        self._setup_tray()
        self.hold()  # la isla vive aunque no haya ventanas "normales"

    def do_activate(self):
        self.window.show_all()

    def do_shutdown(self):
        if self.watcher:
            self.watcher.stop()
        Gtk.Application.do_shutdown(self)

    # --- multimedia -------------------------------------------------------------------

    def on_media(self, state):
        self.state = state
        a = state["active"]
        line = f"{a['name']}: {a['title']} — {a['artist']} ({a['status']})" if a else "sin reproductor"
        if line != self._last_logged:
            self._last_logged = line
            print(f"[islet] {line}", flush=True)
        self.window.set_media(a)
        key = tuple((p["id"], p["status"]) for p in state["players"])
        if key != self._players_key:
            self._players_key = key
            self._refresh_tray_menu()

    def command(self, cmd, arg=None):
        self.watcher.command(cmd, arg)

    # --- menú -------------------------------------------------------------------------

    def build_menu(self):
        menu = Gtk.Menu()

        def item(label, cb=None, sensitive=True):
            it = Gtk.MenuItem(label=label)
            it.set_sensitive(sensitive)
            if cb:
                it.connect("activate", lambda *_: cb())
            menu.append(it)
            return it

        def radio_submenu(label, options):
            sub, group = Gtk.Menu(), None
            for text, active, cb in options:
                r = Gtk.RadioMenuItem.new_with_label_from_widget(group, text)
                group = group or r
                r.set_active(active)
                r.connect("toggled", lambda w, cb=cb: w.get_active() and cb())
                sub.append(r)
            parent = Gtk.MenuItem(label=label)
            parent.set_submenu(sub)
            menu.append(parent)

        item(f"Islet {__version__}", sensitive=False)
        menu.append(Gtk.SeparatorMenuItem())
        players = [("Automático", self.watcher.pinned is None, lambda: self.watcher.select(None))]
        for p in self.state["players"]:
            players.append((f"{p['name']} ({p['status']})", self.watcher.pinned == p["id"],
                            lambda pid=p["id"]: self.watcher.select(pid)))
        radio_submenu("Reproductor", players)

        display = self.window.get_display()
        current = self.window.monitor()
        screens = []
        for i in range(display.get_n_monitors()):
            m = display.get_monitor(i)
            g = m.get_geometry()
            screens.append((f"Pantalla {i + 1} ({g.width}×{g.height})", m == current,
                            lambda i=i: self._set_config("monitor", i, self.window.place)))
        radio_submenu("Pantalla", screens)
        radio_submenu("Tema", [
            (label, self.config["theme"] == key, lambda key=key: self._set_config("theme", key, self.window.queue_draw))
            for key, label in cfg.THEMES.items()
        ])

        auto = Gtk.CheckMenuItem(label="Iniciar con el sistema")
        auto.set_active(cfg.autostart_enabled())
        auto.connect("toggled", lambda w: cfg.set_autostart(w.get_active()))
        menu.append(auto)
        menu.append(Gtk.SeparatorMenuItem())
        item("Salir", self.quit)
        menu.show_all()
        return menu

    def _set_config(self, key, value, then):
        self.config[key] = value
        self.config.save()
        then()

    def popup_menu(self, event=None):
        self._menu = self.build_menu()  # referencia viva mientras está abierto
        self._menu.attach_to_widget(self.window, None)
        self._menu.popup_at_pointer(event)

    # --- bandeja ----------------------------------------------------------------------

    def _setup_tray(self):
        indicator = _load_indicator()
        icon = "islet"
        if indicator:
            self.indicator = indicator.Indicator.new("islet", icon, indicator.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(indicator.IndicatorStatus.ACTIVE)
            self.indicator.set_title("Islet")
            self._refresh_tray_menu()
        else:
            self.status_icon = Gtk.StatusIcon.new_from_icon_name(icon)
            self.status_icon.set_tooltip_text("Islet")
            self.status_icon.connect("popup-menu", lambda _i, _b, _t: self.popup_menu())
            self.status_icon.connect("activate", lambda _i: self.popup_menu())

    def _refresh_tray_menu(self):
        if self.indicator:
            self._tray_menu = self.build_menu()
            self.indicator.set_menu(self._tray_menu)


def main():
    if "--version" in sys.argv:
        print(f"Islet {__version__}")
        return 0
    # WM_CLASS = ("islet", "Islet"): lo usan los escritorios para el icono y las reglas.
    GLib.set_prgname("islet")
    Gdk.set_program_class("Islet")
    app = IsletApp()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, app.quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.quit)
    return app.run([sys.argv[0]])
