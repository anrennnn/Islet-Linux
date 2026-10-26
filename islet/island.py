"""Ventana de la isla: un único DrawingArea pintado con Cairo, sin motor web.

La ventana mide WIN_W×WIN_H y es transparente; la isla se dibuja centrada arriba y su forma
(redondeada) se aplica como forma de entrada, para que los clics fuera de ella pasen a las
ventanas de debajo. Sin compositor (XFWM sin composición, i3, VMs…) también se aplica como
forma visible, así la isla conserva sus esquinas redondeadas.
"""

import math
import os
import threading
import time
import urllib.parse
import urllib.request

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo

WIN_W, WIN_H = 480, 220
TOP_MARGIN = 8
# (ancho, alto, radio) de cada modo; mismas medidas que el diseño original.
SIZES = {"idle": (110, 32, 16), "compact": (240, 36, 18), "expanded": (400, 168, 32)}
ANIM_S = 0.45
FADE_S = 0.3
PEEK_S = 3.5
LEAVE_MS = 350
FONT = "Inter, Cantarell, Noto Sans, Ubuntu, DejaVu Sans, sans-serif"

THEMES = {
    "dark": dict(bg=(0, 0, 0, 1), fg=(1, 1, 1, 1), muted=(1, 1, 1, 0.6), track=(1, 1, 1, 0.18),
                 hover=(1, 1, 1, 0.12), border=None),
    "light": dict(bg=(0.96, 0.96, 0.97, 1), fg=(0.07, 0.07, 0.07, 1), muted=(0, 0, 0, 0.55),
                  track=(0, 0, 0, 0.12), hover=(0, 0, 0, 0.08), border=(0, 0, 0, 0.08)),
    "glass": dict(bg=(0.08, 0.08, 0.094, 0.72), fg=(1, 1, 1, 1), muted=(1, 1, 1, 0.6),
                  track=(1, 1, 1, 0.18), hover=(1, 1, 1, 0.12), border=(1, 1, 1, 0.14)),
}

ICONS = {  # trazados de 24×24 (Material)
    "previous": [((6, 6), (8, 6), (8, 18), (6, 18)), ((9.5, 12), (18, 18), (18, 6))],
    "next": [((16, 6), (18, 6), (18, 18), (16, 18)), ((6, 18), (14.5, 12), (6, 6))],
    "play": [((8, 5), (8, 19), (19, 12))],
    "pause": [((7, 5), (11, 5), (11, 19), (7, 19)), ((13, 5), (17, 5), (17, 19), (13, 19))],
}


def ease(t):
    return 1 - (1 - t) ** 4


def fmt_time(s):
    if not s or s < 0 or not math.isfinite(s):
        s = 0
    return f"{int(s // 60)}:{int(s % 60):02d}"


def rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def rounded_region(x, y, w, h, r):
    """Región de X11 con esquinas redondeadas: una franja por fila de píxeles en las esquinas."""
    r = int(min(r, w // 2, h // 2))
    rects = [cairo.RectangleInt(x, y + r, w, h - 2 * r)]
    for i in range(r):
        dy = r - i - 0.5
        inset = math.ceil(r - math.sqrt(r * r - dy * dy))
        rects.append(cairo.RectangleInt(x + inset, y + i, w - 2 * inset, 1))
        rects.append(cairo.RectangleInt(x + inset, y + h - 1 - i, w - 2 * inset, 1))
    return cairo.Region(rects)


class ArtCache:
    """Carga carátulas (file:// o http/https) fuera del hilo de la interfaz."""

    def __init__(self, on_loaded):
        self.on_loaded = on_loaded
        self.cache = {}
        self.pending = set()

    def get(self, url):
        if not url:
            return None
        if url in self.cache:
            return self.cache[url]
        if url not in self.pending:
            self.pending.add(url)
            threading.Thread(target=self._load, args=(url,), daemon=True).start()
        return None

    def _load(self, url):
        data = None
        try:
            if url.startswith("file://"):
                path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
                if os.path.getsize(path) <= 8 * 1024 * 1024:
                    with open(path, "rb") as f:
                        data = f.read()
            elif url.startswith(("http://", "https://")):
                req = urllib.request.Request(url, headers={"User-Agent": "Islet"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = resp.read(8 * 1024 * 1024)
        except Exception as err:  # una carátula rota no debe tumbar nada
            print(f"[islet] carátula no disponible ({err})", flush=True)
        GLib.idle_add(self._finish, url, data)

    def _finish(self, url, data):
        pixbuf = None
        if data:
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
            except GLib.Error:
                pixbuf = None
        if len(self.cache) > 30:
            self.cache.clear()
        self.cache[url] = pixbuf
        self.pending.discard(url)
        self.on_loaded()
        return GLib.SOURCE_REMOVE


class IslandWindow(Gtk.Window):
    def __init__(self, app, config, on_command, on_menu):
        super().__init__(application=app, title="Islet")
        self.config = config
        self.on_command = on_command
        self.on_menu = on_menu
        self.track = None
        self.received_at = time.monotonic()
        self.hover = False
        self.peek = False
        self.mode = "idle"
        self.prev_mode = "idle"
        self.mode_changed_at = 0.0
        self.anim_from = SIZES["idle"]
        self.geom = SIZES["idle"]
        self.anim_start = 0.0
        self.hot = None  # botón bajo el puntero
        self._tick_id = 0
        self._leave_id = 0
        self._peek_id = 0
        self._shape_key = None
        self.art = ArtCache(self.queue_draw)
        self._scaled = {}  # carátulas ya escaladas, por (pixbuf, tamaño)

        # DOCK: los gestores de ventanas (XFWM, Mutter, KWin, Openbox) respetan su posición,
        # no la decoran, no le dan foco ni la ponen en la barra de tareas y la mantienen encima.
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.stick()
        self.set_app_paintable(True)
        self.set_size_request(WIN_W, WIN_H)
        self.set_default_size(WIN_W, WIN_H)
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        self.area = Gtk.DrawingArea()
        self.area.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
        )
        self.area.connect("draw", self._on_draw)
        self.area.connect("motion-notify-event", self._on_motion)
        self.area.connect("leave-notify-event", lambda *_: self._schedule_leave())
        self.area.connect("button-press-event", self._on_press)
        self.add(self.area)

        self.connect("realize", lambda *_: self._apply_shape(force=True))
        self.connect("map-event", self._on_map)
        self.get_screen().connect("monitors-changed", lambda *_: self.place())
        self.get_screen().connect("composited-changed", lambda *_: self._apply_shape(force=True))
        GLib.timeout_add(80, self._heartbeat)

    # --- posición ---------------------------------------------------------------------

    def monitor(self):
        display = self.get_display()
        idx = self.config.get("monitor")
        if isinstance(idx, int) and 0 <= idx < display.get_n_monitors():
            return display.get_monitor(idx)
        return display.get_primary_monitor() or display.get_monitor(0)

    def place(self):
        wa = self.monitor().get_workarea()
        self.move(wa.x + (wa.width - WIN_W) // 2, wa.y + TOP_MARGIN)

    def _on_map(self, *_):
        # Algunos gestores recolocan la ventana al mapearla; la devolvemos a su sitio.
        self.place()
        GLib.timeout_add(500, lambda: self.place() or False)
        return False

    # --- estado -----------------------------------------------------------------------

    def set_media(self, active):
        old_key = self._track_key(self.track)
        self.track = active if active and (active["title"] or active["status"] == "Playing") else None
        self.received_at = time.monotonic()
        new_key = self._track_key(self.track)
        if new_key and new_key != old_key:
            self._start_peek()
        self._update_mode()
        self.queue_draw()

    @staticmethod
    def _track_key(t):
        return f"{t['id']}|{t['title']}|{t['artist']}" if t else ""

    def set_theme(self, _theme):
        self.queue_draw()

    def _start_peek(self):
        # Al cambiar de canción la isla se abre unos segundos, como en iOS.
        self.peek = True
        if self._peek_id:
            GLib.source_remove(self._peek_id)
        self._peek_id = GLib.timeout_add(int(PEEK_S * 1000), self._end_peek)

    def _end_peek(self):
        self.peek = False
        self._peek_id = 0
        self._update_mode()
        return GLib.SOURCE_REMOVE

    def _update_mode(self):
        mode = "idle" if not self.track else ("expanded" if self.hover or self.peek else "compact")
        if mode == self.mode:
            return
        self.prev_mode, self.mode = self.mode, mode
        self.anim_from = self.geom
        self.anim_start = self.mode_changed_at = time.monotonic()
        self.hot = None
        if not self._tick_id:
            self._tick_id = self.area.add_tick_callback(self._on_tick)

    def _on_tick(self, *_):
        t = min(1.0, (time.monotonic() - self.anim_start) / ANIM_S)
        k = ease(t)
        target = SIZES[self.mode]
        self.geom = tuple(a + (b - a) * k for a, b in zip(self.anim_from, target))
        self._apply_shape()
        self.area.queue_draw()
        if t >= 1.0 and time.monotonic() - self.mode_changed_at >= FADE_S:
            self._tick_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _heartbeat(self):
        # Ecualizador y barra de progreso: ~12 fps solo mientras algo suena.
        if self.track and self.track["status"] == "Playing" and not self._tick_id:
            self.area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def island_rect(self):
        w, h, r = self.geom
        return (WIN_W - w) / 2, 0, w, h, r

    def _apply_shape(self, force=False):
        gdk_win = self.get_window()
        if not gdk_win:
            return
        x, y, w, h, r = self.island_rect()
        key = (round(x), round(w), round(h), round(r))
        if key == self._shape_key and not force:
            return
        self._shape_key = key
        region = rounded_region(int(x), int(y), int(math.ceil(w)), int(math.ceil(h)), r)
        gdk_win.input_shape_combine_region(region, 0, 0)
        composited = self.get_screen().is_composited()
        gdk_win.shape_combine_region(None if composited else region, 0, 0)

    # --- ratón ------------------------------------------------------------------------

    def _inside(self, ex, ey):
        x, y, w, h, _ = self.island_rect()
        return x <= ex <= x + w and y <= ey <= y + h

    def _on_motion(self, _w, ev):
        if self._inside(ev.x, ev.y):
            if self._leave_id:
                GLib.source_remove(self._leave_id)
                self._leave_id = 0
            if not self.hover:
                self.hover = True
                self._update_mode()
            hot = self._hit(ev.x, ev.y)
            if hot != self.hot:
                self.hot = hot
                self.area.queue_draw()
        else:
            self._schedule_leave()
        return False

    def _schedule_leave(self):
        if self.hover and not self._leave_id:
            self._leave_id = GLib.timeout_add(LEAVE_MS, self._on_leave)
        return False

    def _on_leave(self):
        self._leave_id = 0
        self.hover = False
        self.hot = None
        self._update_mode()
        self.area.queue_draw()
        return GLib.SOURCE_REMOVE

    def _controls(self):
        """Zonas activas de la isla expandida: botones y barra de progreso."""
        x, y, w, _h, _r = self.island_rect()
        cx, by = x + w / 2, y + 138
        return {
            "previous": (cx - 58, by, 18),
            "playpause": (cx, by, 18),
            "next": (cx + 58, by, 18),
            "progress": (x + 60, y + 97, w - 120),
        }

    def _hit(self, ex, ey):
        if self.mode != "expanded":
            return None
        for name, (bx, by, r) in self._controls().items():
            if name == "progress":
                if bx <= ex <= bx + r and abs(ey - by) <= 8:
                    return name
            elif (ex - bx) ** 2 + (ey - by) ** 2 <= r * r:
                return name
        return None

    def _on_press(self, _w, ev):
        if not self._inside(ev.x, ev.y):
            return False
        if ev.button == 3:
            self.on_menu(ev)
            return True
        if ev.button != 1 or ev.type != Gdk.EventType.BUTTON_PRESS:
            return False
        hit = self._hit(ev.x, ev.y)
        if hit == "playpause":
            self.on_command("PlayPause")
        elif hit in ("previous", "next"):
            self.on_command(hit.capitalize())
        elif hit == "progress" and self.track and self.track["length"]:
            bx, _by, bw = self._controls()["progress"]
            self.on_command("seek", max(0.0, min(1.0, (ev.x - bx) / bw)) * self.track["length"])
        return True

    # --- dibujo -----------------------------------------------------------------------

    def _position(self):
        t = self.track
        elapsed = time.monotonic() - self.received_at if t["status"] == "Playing" else 0
        pos = t["position"] + elapsed
        return min(pos, t["length"]) if t["length"] > 0 else pos

    def _on_draw(self, _w, cr):
        theme = THEMES.get(self.config.get("theme"), THEMES["dark"])
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        x, y, w, h, r = self.island_rect()
        rounded_rect(cr, x, y, w, h, r)
        cr.set_source_rgba(*theme["bg"])
        cr.fill_preserve()
        if theme["border"]:
            cr.set_source_rgba(*theme["border"])
            cr.set_line_width(1)
            cr.stroke_preserve()
        cr.clip()

        # El contenido aparece con un fundido al cambiar de modo.
        alpha = min(1.0, (time.monotonic() - self.mode_changed_at) / FADE_S)
        cr.push_group()
        if self.mode == "idle":
            self._draw_clock(cr, theme, x, y, w, h)
        elif self.mode == "compact" and self.track:
            self._draw_compact(cr, theme, x, y, w, h)
        elif self.mode == "expanded" and self.track:
            self._draw_expanded(cr, theme, x, y, w)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)
        return True

    def _text(self, cr, text, x, y, size, color, weight=Pango.Weight.NORMAL, width=None,
              align=Pango.Alignment.LEFT, spacing=0, center_y=False):
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription.from_string(FONT)
        desc.set_absolute_size(size * Pango.SCALE)
        desc.set_weight(weight)
        layout.set_font_description(desc)
        if spacing:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
            layout.set_attributes(attrs)
        layout.set_text(text, -1)
        if width:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            layout.set_alignment(align)
        if center_y:
            y -= layout.get_pixel_size()[1] / 2
        cr.set_source_rgba(*color)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    def _draw_clock(self, cr, theme, x, y, w, h):
        self._text(cr, time.strftime("%H:%M"), x, y + h / 2, 13, theme["fg"], Pango.Weight.BOLD,
                   width=w, align=Pango.Alignment.CENTER, center_y=True)

    def _draw_art(self, cr, x, y, size, radius):
        pixbuf = self.art.get(self.track.get("art_url"))
        cr.save()
        rounded_rect(cr, x, y, size, size, radius)
        cr.clip()
        if pixbuf:
            scale = self.get_scale_factor()
            px = int(size * scale)
            key = (id(pixbuf), px)
            scaled = self._scaled.get(key)
            if scaled is None:
                side = min(pixbuf.get_width(), pixbuf.get_height())
                square = pixbuf.new_subpixbuf(
                    (pixbuf.get_width() - side) // 2, (pixbuf.get_height() - side) // 2, side, side
                )
                scaled = square.scale_simple(px, px, GdkPixbuf.InterpType.BILINEAR)
                if len(self._scaled) > 8:
                    self._scaled.clear()
                self._scaled[key] = scaled
            cr.translate(x, y)
            cr.scale(1 / scale, 1 / scale)
            Gdk.cairo_set_source_pixbuf(cr, scaled, 0, 0)
            cr.paint()
        else:
            grad = cairo.LinearGradient(x, y, x + size, y + size)
            grad.add_color_stop_rgb(0, 0.357, 0.357, 0.941)
            grad.add_color_stop_rgb(1, 0.753, 0.31, 0.847)
            cr.set_source(grad)
            cr.paint()
            self._text(cr, "♪", x, y + size / 2, size * 0.45, (1, 1, 1, 1), width=size,
                       align=Pango.Alignment.CENTER, center_y=True)
        cr.restore()

    def _draw_bars(self, cr, theme, right, cy, playing):
        now = time.monotonic()
        for i in range(4):
            if playing:
                k = 0.25 + 0.75 * abs(math.sin(now * 3.4 + i * 1.3))
            else:
                k = 0.3
            bh = 14 * k
            bx = right - 18 + i * 5
            rounded_rect(cr, bx, cy + 7 - bh, 3, bh, 1.5)
            cr.set_source_rgba(*theme["fg"])
            cr.fill()

    def _draw_compact(self, cr, theme, x, y, w, h):
        t = self.track
        self._draw_art(cr, x + 6, y + (h - 24) / 2, 24, 12)
        self._text(cr, t["title"] or t["name"], x + 40, y + h / 2, 12, theme["fg"], Pango.Weight.BOLD,
                   width=w - 40 - 12 - 18 - 10, center_y=True)
        self._draw_bars(cr, theme, x + w - 12, y + h / 2, t["status"] == "Playing")

    def _draw_expanded(self, cr, theme, x, y, w):
        t = self.track
        playing = t["status"] == "Playing"
        self._draw_art(cr, x + 20, y + 16, 56, 8)
        tx, tw = x + 88, w - 88 - 20 - 18 - 12
        self._text(cr, t["title"] or "Sin título", tx, y + 17, 15, theme["fg"], Pango.Weight.BOLD, width=tw)
        self._text(cr, t["artist"] or t["album"] or "—", tx, y + 39, 13, theme["muted"], width=tw)
        self._text(cr, t["name"].upper(), tx, y + 59, 10, theme["muted"], width=tw, spacing=0.8)
        self._draw_bars(cr, theme, x + w - 20, y + 44, playing)

        controls = self._controls()
        bx, by, bw = controls["progress"]
        pos = self._position()
        self._text(cr, fmt_time(pos), x + 20, by, 11, theme["muted"], center_y=True)
        self._text(cr, fmt_time(t["length"]) if t["length"] else "--:--", bx + bw + 6, by, 11,
                   theme["muted"], width=34, align=Pango.Alignment.RIGHT, center_y=True)
        rounded_rect(cr, bx, by - 2.5, bw, 5, 2.5)
        cr.set_source_rgba(*theme["track"])
        cr.fill()
        if t["length"] > 0:
            rounded_rect(cr, bx, by - 2.5, max(5, bw * pos / t["length"]), 5, 2.5)
            cr.set_source_rgba(*theme["fg"])
            cr.fill()

        for name in ("previous", "playpause", "next"):
            cx, cy, rr = controls[name]
            if self.hot == name:
                cr.arc(cx, cy, rr, 0, 2 * math.pi)
                cr.set_source_rgba(*theme["hover"])
                cr.fill()
            icon = ("pause" if playing else "play") if name == "playpause" else name
            size = 26 if name == "playpause" else 20
            cr.save()
            cr.translate(cx - size / 2, cy - size / 2)
            cr.scale(size / 24, size / 24)
            for poly in ICONS[icon]:
                cr.move_to(*poly[0])
                for pt in poly[1:]:
                    cr.line_to(*pt)
                cr.close_path()
            cr.set_source_rgba(*theme["fg"])
            cr.fill()
            cr.restore()
