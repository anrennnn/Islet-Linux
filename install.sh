#!/usr/bin/env bash
# Instalador de Islet: detecta tu distro y arquitectura e instala el paquete correcto
# desde la última release de GitHub.
#
#   curl -fsSL https://raw.githubusercontent.com/anrennnn/Islet-Linux/main/install.sh | bash
#
# Opciones:  --appimage   fuerza la versión AppImage (sin root)
#            --uninstall  desinstala Islet
set -euo pipefail

REPO="anrennnn/Islet-Linux"
APP="islet"
MODE="auto"
for arg in "$@"; do
  case "$arg" in
    --appimage) MODE="appimage" ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) echo "Uso: install.sh [--appimage|--uninstall]"; exit 0 ;;
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

case "$(uname -m)" in
  x86_64|amd64) ARCH_RE='x86_64|amd64|x64' ;;
  aarch64|arm64) ARCH_RE='aarch64|arm64' ;;
  *) die "Arquitectura no soportada: $(uname -m)" ;;
esac

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
    *) echo appimage ;;
  esac
}

APPIMAGE_PATH="$HOME/.local/bin/$APP"
DESKTOP_PATH="$HOME/.local/share/applications/$APP.desktop"

uninstall() {
  say "Desinstalando Islet"
  if have dpkg && dpkg -s "$APP" >/dev/null 2>&1; then $SUDO apt-get remove -y "$APP"
  elif have rpm && rpm -q "$APP" >/dev/null 2>&1; then
    if have dnf; then $SUDO dnf remove -y "$APP"; elif have zypper; then $SUDO zypper -n remove "$APP"; else $SUDO rpm -e "$APP"; fi
  elif have pacman && pacman -Q "$APP" >/dev/null 2>&1; then $SUDO pacman -R --noconfirm "$APP"
  fi
  rm -f "$APPIMAGE_PATH" "$DESKTOP_PATH" "$HOME/.local/share/icons/$APP.png" "$HOME/.config/autostart/$APP.desktop"
  say "Listo"
}
[ "$MODE" = uninstall ] && { uninstall; exit 0; }

have curl || die "Necesitas curl"
FAMILY=$( [ "$MODE" = appimage ] && echo appimage || family )
case "$FAMILY" in
  deb) EXT='deb' ;;
  rpm-*) EXT='rpm' ;;
  pacman) EXT='pacman' ;;
  appimage) EXT='AppImage' ;;
esac
# Sin sudo no podemos instalar paquetes del sistema: AppImage en el directorio del usuario.
if [ "$EXT" != AppImage ] && [ "$(id -u)" -ne 0 ] && [ -z "$SUDO" ]; then
  say "No hay sudo/doas, uso AppImage"; EXT='AppImage'; FAMILY=appimage
fi

say "Distro: ${PRETTY_NAME:-desconocida} · arquitectura: $(uname -m) · paquete: .$EXT"
API="https://api.github.com/repos/$REPO/releases/latest"
URL=$(curl -fsSL "$API" | grep -oE '"browser_download_url": *"[^"]+"' | cut -d'"' -f4 \
  | grep -E "\.${EXT}\$" | grep -E "$ARCH_RE" | head -n1) || true
[ -n "$URL" ] || die "No encontré un .$EXT para $(uname -m) en la última release de $REPO"

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
FILE="$TMP/$(basename "$URL")"
say "Descargando $(basename "$URL")"
curl -fL --progress-bar -o "$FILE" "$URL"

case "$FAMILY" in
  deb) $SUDO apt-get install -y "$FILE" ;;
  rpm-dnf) if have dnf; then $SUDO dnf install -y "$FILE"; else $SUDO yum install -y "$FILE"; fi ;;
  rpm-zypper) $SUDO zypper -n install --allow-unsigned-rpm "$FILE" ;;
  pacman) $SUDO pacman -U --noconfirm "$FILE" ;;
  appimage)
    mkdir -p "$(dirname "$APPIMAGE_PATH")" "$(dirname "$DESKTOP_PATH")" "$HOME/.local/share/icons"
    install -m 755 "$FILE" "$APPIMAGE_PATH"
    curl -fsSL -o "$HOME/.local/share/icons/$APP.png" "https://raw.githubusercontent.com/$REPO/main/build/icon.png" || true
    cat > "$DESKTOP_PATH" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Islet
Comment=Isla dinámica con controles multimedia
Exec=$APPIMAGE_PATH
Icon=$HOME/.local/share/icons/$APP.png
Categories=Utility;AudioVideo;
DESKTOP
    if ! ldconfig -p 2>/dev/null | grep -q libfuse.so.2; then
      say "Aviso: AppImage necesita FUSE 2 (libfuse2 / fuse2 / fuse-libs según tu distro)."
      say "Sin FUSE puedes ejecutarlo con: $APPIMAGE_PATH --appimage-extract-and-run"
    fi
    case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) say "Añade ~/.local/bin a tu PATH para lanzar 'islet' desde la terminal" ;; esac
    ;;
esac

say "Islet instalado. Ábrelo desde el menú de aplicaciones o con: islet"
