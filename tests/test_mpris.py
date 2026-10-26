#!/usr/bin/env python3
"""Prueba de humo del cliente MPRIS contra tools/fake_player.py (en un bus de sesión)."""

import os
import subprocess
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import GLib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from islet.mpris import MprisWatcher  # noqa: E402

state = {}
loop = GLib.MainLoop()


def on_change(s):
    state.update(s)


def wait(cond, timeout=5.0):
    deadline = GLib.get_monotonic_time() + int(timeout * 1e6)
    ctx = loop.get_context()
    while not cond():
        if GLib.get_monotonic_time() > deadline:
            raise AssertionError(f"tiempo agotado; estado: {state.get('active')}")
        ctx.iteration(True)


fake = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "fake_player.py")], stdout=subprocess.PIPE, text=True)
try:
    assert "listo" in fake.stdout.readline()
    w = MprisWatcher(on_change)
    w.start()
    active = lambda: state.get("active") or {}  # noqa: E731
    wait(lambda: active().get("title") == "Midnight City")
    assert active()["name"] == "Fake Player" or wait(lambda: active()["name"] == "Fake Player") is None
    assert active()["status"] == "Playing" and active()["length"] == 244
    w.command("PlayPause")
    wait(lambda: active()["status"] == "Paused")
    w.command("Next")
    wait(lambda: active()["title"] == "Blinding Lights" and active()["artist"] == "The Weeknd")
    w.command("seek", 100)
    wait(lambda: round(active()["position"]) == 100)
    fake.kill()
    wait(lambda: state.get("active") is None)
    print("MPRIS OK")
finally:
    fake.kill()
