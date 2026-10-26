#!/usr/bin/env bash
# Construye los paquetes de Islet en dist/:
#   islet_<v>_all.deb        Debian, Ubuntu, Mint, Pop!_OS, Xubuntu…  (siempre)
#   islet-<v>.tar.gz         portable, sin root                        (siempre)
#   islet-<v>-1.noarch.rpm   Fedora, openSUSE                          (si hay fpm + rpmbuild)
#   islet-<v>-1-any.pkg.tar.zst  Arch, Manjaro                         (si hay fpm + bsdtar)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/islet/__init__.py")
OUT="$ROOT/dist"; STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
rm -rf "$OUT"; mkdir -p "$OUT"
echo "Islet $VERSION"

# --- árbol de instalación común -------------------------------------------------------
R="$STAGE/root"
install -d "$R/usr/bin" "$R/usr/share/islet/islet" "$R/usr/share/applications" "$R/usr/share/doc/islet"
install -m 644 "$ROOT"/islet/*.py "$R/usr/share/islet/islet/"
sed "s|@LIBDIR@|/usr/share/islet|" "$ROOT/packaging/islet.sh" > "$R/usr/bin/islet"
chmod 755 "$R/usr/bin/islet"
install -m 644 "$ROOT/data/islet.desktop" "$R/usr/share/applications/islet.desktop"
for s in 48 128 256; do
  install -Dm 644 "$ROOT/data/icons/islet-$s.png" "$R/usr/share/icons/hicolor/${s}x${s}/apps/islet.png"
done
install -Dm 644 "$ROOT/data/icons/islet.png" "$R/usr/share/icons/hicolor/512x512/apps/islet.png"
install -m 644 "$ROOT/LICENSE" "$R/usr/share/doc/islet/copyright"

# --- .deb -------------------------------------------------------------------------------
D="$STAGE/deb"; cp -a "$R" "$D"; install -d "$D/DEBIAN"
cat > "$D/DEBIAN/control" <<CTRL
Package: islet
Version: $VERSION
Architecture: all
Maintainer: Anthony <seoconanthony@gmail.com>
Installed-Size: $(du -sk "$R" | cut -f1)
Depends: python3 (>= 3.8), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0
Recommends: gir1.2-ayatanaappindicator3-0.1
Section: sound
Priority: optional
Homepage: https://github.com/anrennnn/Islet-Linux
Description: Isla dinámica con controles multimedia para Linux
 Píldora flotante en la parte superior de la pantalla (estilo iPhone) que muestra
 la canción que suena en cualquier reproductor MPRIS (Spotify, VLC, Firefox,
 Chromium, Rhythmbox, Parole, Audacious, mpv…) con carátula, progreso y botones
 de anterior, reproducir/pausa y siguiente. Hecha con Python y GTK 3: ligera y
 pensada para XFCE, pero funciona en GNOME, KDE, Cinnamon, MATE y otros.
CTRL
cat > "$D/DEBIAN/postinst" <<'SCRIPT'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
  command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
fi
exit 0
SCRIPT
cp "$D/DEBIAN/postinst" "$D/DEBIAN/postrm"
sed -i 's/if \[ "$1" = configure \]; then/if [ "$1" = remove ] || [ "$1" = purge ]; then/' "$D/DEBIAN/postrm"
chmod 755 "$D/DEBIAN/postinst" "$D/DEBIAN/postrm"
find "$D" -type d -exec chmod 755 {} +
dpkg-deb --root-owner-group --build "$D" "$OUT/islet_${VERSION}_all.deb" >/dev/null
echo "  dist/islet_${VERSION}_all.deb"

# --- portable (.tar.gz) -----------------------------------------------------------------
P="$STAGE/islet-$VERSION"; install -d "$P"
cp -a "$ROOT/islet" "$ROOT/data" "$ROOT/LICENSE" "$ROOT/README.md" "$P/"
find "$P" -name __pycache__ -prune -exec rm -rf {} +
install -m 755 "$ROOT/packaging/islet.sh" "$P/islet.py"
tar -C "$STAGE" -czf "$OUT/islet-$VERSION.tar.gz" "islet-$VERSION"
echo "  dist/islet-$VERSION.tar.gz"

# --- rpm y pacman (opcionales) ----------------------------------------------------------
if command -v fpm >/dev/null; then
  COMMON=(-s dir -C "$R" -n islet -v "$VERSION" --iteration 1 -a all --license MIT
          --url https://github.com/anrennnn/Islet-Linux --maintainer "Anthony <seoconanthony@gmail.com>"
          --description "Isla dinámica con controles multimedia (MPRIS) para Linux")
  if command -v rpmbuild >/dev/null; then
    # Fedora: gtk3 y python3-gobject ya traen el typelib y el puente con cairo.
    # openSUSE: "gtk3" lo cumple libgtk-3-0, que no trae typelib ni puente: se piden aparte.
    fpm "${COMMON[@]}" -t rpm -p "$OUT/islet-$VERSION-1.noarch.rpm" --rpm-os linux \
      -d python3 -d python3-gobject -d gtk3 \
      -d "(typelib-1_0-Gtk-3_0 if libgtk-3-0)" -d "(python3-gobject-cairo if libgtk-3-0)" . >/dev/null
    echo "  dist/islet-$VERSION-1.noarch.rpm"
  fi
  if command -v bsdtar >/dev/null; then
    fpm "${COMMON[@]}" -t pacman -p "$OUT/islet-$VERSION-1-any.pkg.tar.zst" \
      -d python -d python-gobject -d python-cairo -d gtk3 --pacman-optional-depends libayatana-appindicator --pacman-compression zstd . >/dev/null
    echo "  dist/islet-$VERSION-1-any.pkg.tar.zst"
  fi
fi
