"""Cliente MPRIS (org.mpris.MediaPlayer2) sobre D-Bus con Gio.

Funciona con Spotify, VLC, Firefox, Chromium, Rhythmbox, Parole, Audacious, mpv (mpv-mpris),
Elisa, etc. Todas las llamadas son asíncronas para que un reproductor colgado no congele la isla.
"""

import time

from gi.repository import Gio, GLib

MPRIS_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
TIMEOUT_MS = 2000


class Player:
    def __init__(self, bus_name, owner):
        self.bus_name = bus_name
        self.owner = owner
        self.identity = None
        self.status = "Stopped"
        self.metadata = {}
        self.can_control = True
        self.position = 0  # microsegundos
        self.position_at = time.monotonic()
        self.last_active = 0.0
        self.subscriptions = []

    @property
    def name(self):
        return self.identity or self.bus_name[len(MPRIS_PREFIX):].split(".")[0]

    def apply_props(self, changed):
        if "PlaybackStatus" in changed:
            self.status = changed["PlaybackStatus"]
            if self.status == "Playing":
                self.last_active = time.monotonic()
        if "Metadata" in changed:
            self.metadata = dict(changed["Metadata"] or {})
            self.last_active = time.monotonic()
            self.set_position(0)
        if "CanControl" in changed:
            self.can_control = bool(changed["CanControl"])
        if "Position" in changed:
            self.set_position(int(changed["Position"]))

    def set_position(self, us):
        self.position = us
        self.position_at = time.monotonic()

    def estimated_position(self):
        drift = (time.monotonic() - self.position_at) * 1e6 if self.status == "Playing" else 0
        return self.position + drift

    def snapshot(self):
        md = self.metadata
        artist = md.get("xesam:artist") or ""
        if isinstance(artist, (list, tuple)):
            artist = ", ".join(artist)
        length = int(md.get("mpris:length") or 0) / 1e6
        position = self.estimated_position() / 1e6
        if length > 0:
            position = min(position, length)
        return {
            "id": self.bus_name,
            "name": self.name,
            "status": self.status,
            "title": md.get("xesam:title") or "",
            "artist": artist,
            "album": md.get("xesam:album") or "",
            "art_url": md.get("mpris:artUrl") or None,
            "track_id": md.get("mpris:trackid") or None,
            "length": length,
            "position": max(0.0, position),
            "can_control": self.can_control,
        }


class MprisWatcher:
    """Vigila los reproductores MPRIS del bus de sesión y llama a on_change(state)."""

    def __init__(self, on_change):
        self.on_change = on_change
        self.players = {}
        self.pinned = None
        self.bus = None
        self._poll_id = 0

    def start(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.bus.signal_subscribe(
            "org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged",
            "/org/freedesktop/DBus", None, Gio.DBusSignalFlags.NONE, self._on_name_owner_changed,
        )
        self.bus.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames",
            None, GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, TIMEOUT_MS, None, self._on_list_names,
        )
        # Corrige la deriva de la posición estimada cada pocos segundos.
        self._poll_id = GLib.timeout_add_seconds(3, self._refresh_positions)

    def stop(self):
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0

    # --- descubrimiento ---------------------------------------------------------------

    def _on_list_names(self, bus, result):
        try:
            (names,) = bus.call_finish(result).unpack()
        except GLib.Error as err:
            print(f"[mpris] ListNames falló: {err.message}", flush=True)
            return
        for name in names:
            if name.startswith(MPRIS_PREFIX):
                self._resolve_owner(name)
        self._emit()

    def _on_name_owner_changed(self, _bus, _sender, _path, _iface, _signal, params):
        name, _old, new = params.unpack()
        if not name.startswith(MPRIS_PREFIX):
            return
        if new:
            self._remove_player(name)
            self._add_player(name, new)
        else:
            self._remove_player(name)

    def _resolve_owner(self, name):
        def done(bus, result):
            try:
                (owner,) = bus.call_finish(result).unpack()
            except GLib.Error:
                return
            self._add_player(name, owner)

        self.bus.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner",
            GLib.Variant("(s)", (name,)), GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE,
            TIMEOUT_MS, None, done,
        )

    def _add_player(self, name, owner):
        if name in self.players:
            return
        player = Player(name, owner)
        self.players[name] = player
        # Las señales llegan con el nombre único como emisor, así que filtramos por él.
        player.subscriptions = [
            self.bus.signal_subscribe(
                owner, PROPS_IFACE, "PropertiesChanged", MPRIS_PATH, None,
                Gio.DBusSignalFlags.NONE, self._on_props_changed, player,
            ),
            self.bus.signal_subscribe(
                owner, PLAYER_IFACE, "Seeked", MPRIS_PATH, None,
                Gio.DBusSignalFlags.NONE, self._on_seeked, player,
            ),
        ]

        def got_all(bus, result):
            try:
                (props,) = bus.call_finish(result).unpack()
            except GLib.Error as err:
                print(f"[mpris] no se pudo leer {name}: {err.message}", flush=True)
                return
            player.apply_props(props)
            self._emit()

        def got_identity(bus, result):
            try:
                (value,) = bus.call_finish(result).unpack()
                player.identity = value
                self._emit()
            except GLib.Error:
                pass

        self._call(owner, PROPS_IFACE, "GetAll", GLib.Variant("(s)", (PLAYER_IFACE,)), got_all)
        self._call(owner, PROPS_IFACE, "Get", GLib.Variant("(ss)", (ROOT_IFACE, "Identity")), got_identity)

    def _remove_player(self, name):
        player = self.players.pop(name, None)
        if not player:
            return
        for sub in player.subscriptions:
            self.bus.signal_unsubscribe(sub)
        if self.pinned == name:
            self.pinned = None
        self._emit()

    # --- señales ----------------------------------------------------------------------

    def _on_props_changed(self, _bus, _sender, _path, _iface, _signal, params, player):
        iface, changed, _invalidated = params.unpack()
        if iface != PLAYER_IFACE:
            return
        player.apply_props(changed)
        self._emit()

    def _on_seeked(self, _bus, _sender, _path, _iface, _signal, params, player):
        (pos,) = params.unpack()
        player.set_position(int(pos))
        self._emit()

    def _refresh_positions(self):
        for player in list(self.players.values()):
            if player.status != "Playing":
                continue

            def done(bus, result, player=player):
                try:
                    (value,) = bus.call_finish(result).unpack()
                    player.set_position(int(value))
                except GLib.Error:
                    pass

            self._call(player.owner, PROPS_IFACE, "Get", GLib.Variant("(ss)", (PLAYER_IFACE, "Position")), done)
        return GLib.SOURCE_CONTINUE

    # --- estado y comandos ------------------------------------------------------------

    def active(self):
        """Fijado > el que suena más reciente > el último activo."""
        if self.pinned in self.players:
            return self.players[self.pinned]
        players = list(self.players.values())
        playing = [p for p in players if p.status == "Playing"]
        pool = playing or players
        return max(pool, key=lambda p: p.last_active) if pool else None

    def state(self):
        active = self.active()
        return {
            "active": active.snapshot() if active else None,
            "players": [{"id": p.bus_name, "name": p.name, "status": p.status} for p in self.players.values()],
        }

    def _emit(self):
        self.on_change(self.state())

    def select(self, bus_name):
        self.pinned = bus_name
        self._emit()

    def command(self, cmd, arg=None):
        player = self.active()
        if not player:
            return
        if cmd in ("PlayPause", "Next", "Previous"):
            self._call(player.owner, PLAYER_IFACE, cmd, None)
        elif cmd == "seek":
            track_id = player.metadata.get("mpris:trackid")
            if not track_id or not GLib.Variant.is_object_path(track_id):
                return
            us = max(0, int(float(arg) * 1e6))
            self._call(player.owner, PLAYER_IFACE, "SetPosition", GLib.Variant("(ox)", (track_id, us)))
            player.set_position(us)
            self._emit()

    def _call(self, owner, iface, method, params, callback=None):
        def done(bus, result):
            try:
                bus.call_finish(result)
            except GLib.Error as err:
                print(f"[mpris] {method} falló: {err.message}", flush=True)

        self.bus.call(
            owner, MPRIS_PATH, iface, method, params, None, Gio.DBusCallFlags.NONE,
            TIMEOUT_MS, None, callback or done,
        )
