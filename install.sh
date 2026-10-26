#!/usr/bin/env bash
# Instalador de Islet: detecta tu distro e instala el paquete correcto de la última release.
#
#   curl -fsSL https://raw.githubusercontent.com/anrennnn/Islet-Linux/main/install.sh | bash
#
# Opciones:  --portable   instala en tu carpeta de usuario, sin root
#            --uninstall  desinstala Islet
# Variables: ISLET_LOCAL_DIR=<carpeta> instala desde paquetes ya descargados (sin internet)
set -euo pipefail

REPO="anrennnn/Islet-Linux"
APP="islet"
MODE="auto"
for arg in "$@"; do
  case "$arg" in
    --portable|--appimage) MODE="portable" ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) echo "Uso: install.sh [--portable|--uninstall]"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 1 ;;
  esac
done

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if have sudo; then SUDO="sudo"; elif have doas; then SUDO="doas"; fi
fi

DISTRO_ID=""; DISTRO_LIKE=""
if [ -r /etc/os-release ]; then
  . /etc/os-release
  DISTRO_ID="${ID:-}"; DISTRO_LIKE="${ID_LIKE:-}"
fi
family() {
  case " $DISTRO_ID $DISTRO_LIKE " in
    *" debian "*|*" ubuntu "*) echo deb ;;
    *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*|*" nobara "*) echo rpm-dnf ;;
    *" opensuse"*|*" suse "*|*" sles "*) echo rpm-zypper ;;
    *" arch "*|*" manjaro "*|*" endeavouros "*|*" cachyos "*|*" garuda "*) echo pacman ;;
    *) echo portable ;;
  esac
}

PORTABLE_DIR="$HOME/.local/lib/$APP"
LAUNCHER_PATH="$HOME/.local/bin/$APP"
DESKTOP_PATH="$HOME/.local/share/applications/$APP.desktop"
ICON_PATH="$HOME/.local/share/icons/hicolor/256x256/apps/$APP.png"

uninstall() {
  say "Desinstalando Islet"
  pkill -x "$APP" 2>/dev/null || pkill -f "/usr/bin/$APP" 2>/dev/null || true
  if have dpkg && dpkg -s "$APP" >/dev/null 2>&1; then $SUDO apt-get remove -y "$APP"
  elif have rpm && rpm -q "$APP" >/dev/null 2>&1; then
    if have dnf; then $SUDO dnf remove -y "$APP"; elif have zypper; then $SUDO zypper -n remove "$APP"; else $SUDO rpm -e "$APP"; fi
  elif have pacman && pacman -Q "$APP" >/dev/null 2>&1; then $SUDO pacman -R --noconfirm "$APP"
  fi
  rm -rf "$PORTABLE_DIR"; rm -f "$LAUNCHER_PATH" "$DESKTOP_PATH" "$ICON_PATH" "$HOME/.config/autostart/$APP.desktop"
  say "Listo"
}
[ "$MODE" = uninstall ] && { uninstall; exit 0; }

FAMILY=$( [ "$MODE" = portable ] && echo portable || family )
# Sin sudo no podemos instalar paquetes del sistema: versión portable en el directorio del usuario.
if [ "$FAMILY" != portable ] && [ "$(id -u)" -ne 0 ] && [ -z "$SUDO" ]; then
  say "No hay sudo/doas, instalo la versión portable"; FAMILY=portable
fi
case "$FAMILY" in
  deb) PATTERN='_all\.deb$' ;;
  rpm-*) PATTERN='\.noarch\.rpm$' ;;
  pacman) PATTERN='\.pkg\.tar\.zst$' ;;
  portable) PATTERN='^islet-[0-9.]+\.tar\.gz$' ;;
esac

say "Distro: ${PRETTY_NAME:-desconocida} · instalación: $FAMILY"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
chmod a+rx "$TMP"  # apt descarga privilegios al usuario _apt y necesita leer el paquete
if [ -n "${ISLET_LOCAL_DIR:-}" ]; then
  NAME=$(ls "$ISLET_LOCAL_DIR" | grep -E "$PATTERN" | head -n1) || true
  [ -n "$NAME" ] || die "No hay un paquete $FAMILY en $ISLET_LOCAL_DIR"
  cp "$ISLET_LOCAL_DIR/$NAME" "$TMP/$NAME"
else
  have curl || die "Necesitas curl"
  AUTH=(); [ -n "${GITHUB_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GITHUB_TOKEN")
  URL=$(curl -fsSL "${AUTH[@]}" "https://api.github.com/repos/$REPO/releases/latest" \
    | grep -oE '"browser_download_url": *"[^"]+"' | cut -d'"' -f4 \
    | while read -r u; do basename "$u" | grep -qE "$PATTERN" && echo "$u"; done | head -n1) || true
  [ -n "$URL" ] || die "No encontré un paquete $FAMILY en la última release de $REPO"
  NAME=$(basename "$URL")
  say "Descargando $NAME"
  curl -fL --progress-bar -o "$TMP/$NAME" "$URL"
fi
FILE="$TMP/$NAME"
chmod a+r "$FILE"

# Comprueba que el sistema tiene Python 3 con GTK 3 (lo que necesita la versión portable).
check_gtk() {
  python3 - <<'PY' 2>/dev/null
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, PangoCairo  # noqa
import cairo  # noqa
from gi.repository import cairo as gicairo  # noqa: el puente gi-cairo
PY
}

case "$FAMILY" in
  deb) $SUDO apt-get install -y "$FILE" ;;
  rpm-dnf) if have dnf; then $SUDO dnf install -y "$FILE"; else $SUDO yum install -y "$FILE"; fi ;;
  rpm-zypper) $SUDO zypper -n install --allow-unsigned-rpm "$FILE" ;;
  pacman) $SUDO pacman -U --noconfirm "$FILE" ;;
  portable)
    have tar || die "Necesitas tar"
    if ! have python3 || ! check_gtk; then
      say "Falta Python 3 con GTK 3. Instálalo con el gestor de paquetes de tu distro:"
      echo "   Debian/Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"
      echo "   Fedora:        sudo dnf install python3-gobject gtk3"
      echo "   openSUSE:      sudo zypper install python3-gobject python3-gobject-cairo typelib-1_0-Gtk-3_0"
      echo "   Arch:          sudo pacman -S python-gobject python-cairo gtk3"
      echo "   Void:          sudo xbps-install python3-gobject gtk+3"
      echo "   Alpine:        sudo apk add py3-gobject3 py3-cairo gtk+3.0"
      die "Dependencias que faltan"
    fi
    mkdir -p "$PORTABLE_DIR" "$(dirname "$LAUNCHER_PATH")" "$(dirname "$DESKTOP_PATH")" "$(dirname "$ICON_PATH")"
    rm -rf "${PORTABLE_DIR:?}"/*
    tar -xzf "$FILE" -C "$PORTABLE_DIR" --strip-components=1
    ln -sf "$PORTABLE_DIR/islet.py" "$LAUNCHER_PATH"
    cp "$PORTABLE_DIR/data/icons/islet-256.png" "$ICON_PATH"
    sed "s|^Exec=.*|Exec=$LAUNCHER_PATH|" "$PORTABLE_DIR/data/islet.desktop" > "$DESKTOP_PATH"
    case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) say "Añade ~/.local/bin a tu PATH para lanzar 'islet' desde la terminal" ;; esac
    ;;
esac

say "Islet instalado. Ábrelo desde el menú de aplicaciones o con: islet"
