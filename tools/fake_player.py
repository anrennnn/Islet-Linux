#!/usr/bin/env python3
"""Reproductor MPRIS falso para probar Islet sin Spotify/VLC.

Uso: python3 tools/fake_player.py
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

TRACKS = [
    ("Midnight City", "M83", 244),
    ("Blinding Lights", "The Weeknd", 200),
]

XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <property name="Identity" type="s" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="PlayPause"/>
    <method name="Next"/>
    <method name="Previous"/>
    <method name="SetPosition"><arg type="o" direction="in"/><arg type="x" direction="in"/></method>
    <signal name="Seeked"><arg type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="CanControl" type="b" access="read"/>
    <property name="Position" type="x" access="read"/>
    <property name="Metadata" type="a{sv}" access="read"/>
  </interface>
</node>
"""

PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"


class FakePlayer:
    def __init__(self):
        self.i = 0
        self.status = "Playing"
        self.pos = 0
        self.conn = None

    def metadata(self):
        title, artist, length = TRACKS[self.i]
        return GLib.Variant("a{sv}", {
            "mpris:trackid": GLib.Variant("o", f"/fake/track/{self.i}"),
            "mpris:length": GLib.Variant("x", length * 1_000_000),
            "xesam:title": GLib.Variant("s", title),
            "xesam:artist": GLib.Variant("as", [artist]),
        })

    def prop(self, iface, name):
        if iface == "org.mpris.MediaPlayer2":
            return GLib.Variant("s", "Fake Player")
        return {
            "PlaybackStatus": lambda: GLib.Variant("s", self.status),
            "CanControl": lambda: GLib.Variant("b", True),
            "Position": lambda: GLib.Variant("x", self.pos),
            "Metadata": self.metadata,
        }[name]()

    def changed(self, **props):
        self.conn.emit_signal(
            None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", (PLAYER, props, [])),
        )

    def on_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method == "PlayPause":
            self.status = "Paused" if self.status == "Playing" else "Playing"
            self.changed(PlaybackStatus=GLib.Variant("s", self.status))
        elif method in ("Next", "Previous"):
            step = 1 if method == "Next" else -1
            self.i = (self.i + step) % len(TRACKS)
            self.pos = 0
            self.changed(Metadata=self.metadata())
        elif method == "SetPosition":
            _track, self.pos = params.unpack()
            self.conn.emit_signal(None, PATH, PLAYER, "Seeked", GLib.Variant("(x)", (self.pos,)))
        invocation.return_value(None)

    def on_get(self, _conn, _sender, _path, iface, name):
        return self.prop(iface, name)

    def on_bus(self, conn, _name):
        self.conn = conn
        for iface in Gio.DBusNodeInfo.new_for_xml(XML).interfaces:
            conn.register_object(PATH, iface, self.on_call, self.on_get, None)

    def on_name(self, _conn, _name):
        print("Fake MPRIS player listo", flush=True)


if __name__ == "__main__":
    player = FakePlayer()
    Gio.bus_own_name(
        Gio.BusType.SESSION, "org.mpris.MediaPlayer2.fakeplayer", Gio.BusNameOwnerFlags.NONE,
        player.on_bus, player.on_name, None,
    )
    GLib.MainLoop().run()
