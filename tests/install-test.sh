#!/usr/bin/env bash
# Prueba de instalación de extremo a extremo dentro de un contenedor de la distro.
#   bash tests/install-test.sh            → instala desde ISLET_LOCAL_DIR o desde la última release
#   bash tests/install-test.sh --appimage → prueba la vía AppImage
# Comprueba: install.sh termina bien, el binario existe, la app arranca, crea su ventana
# y lee un reproductor MPRIS de prueba por D-Bus.
set -euo pipefail
MODE_ARG="${1:-}"
HERE=$(cd "$(dirname "$0")/.." && pwd)
. /etc/os-release
echo "### $PRETTY_NAME ($(uname -m)) ${MODE_ARG}"

# Dependencias del entorno de prueba (no de Islet): curl, sudo, X virtual, D-Bus.
case " $ID $ID_LIKE " in
  *" debian "*|*" ubuntu "*)
    export DEBIAN_FRONTEND=noninteractive
    apt-get -qq update && apt-get -qq install -y curl ca-certificates sudo xvfb xauth x11-utils dbus dbus-x11 >/dev/null ;;
  *" fedora "*|*" rhel "*)
    dnf -q -y install curl sudo xorg-x11-server-Xvfb xorg-x11-xauth xwininfo dbus-daemon dbus-tools which findutils procps-ng >/dev/null ;;
  *" suse "*|*" opensuse"*)
    zypper -q -n install curl sudo xvfb-run xwininfo dbus-1 which findutils procps >/dev/null ;;
  *" arch "*)
    pacman -Syu --noconfirm --needed -q curl sudo xorg-server-xvfb xorg-xauth xorg-xwininfo dbus which findutils procps-ng >/dev/null ;;
esac

# Un escritorio real ya trae estas librerías; el AppImage las usa del sistema.
if [ "$MODE_ARG" = --appimage ]; then
  case " $ID $ID_LIKE " in
    *" debian "*|*" ubuntu "*) apt-get -qq install -y libgtk-3-0t64 libnss3 libasound2t64 libgbm1 libxss1 libxtst6 >/dev/null 2>&1 \
      || apt-get -qq install -y libgtk-3-0 libnss3 libasound2 libgbm1 libxss1 libxtst6 >/dev/null ;;
    *" fedora "*) dnf -q -y install gtk3 nss alsa-lib mesa-libgbm libXScrnSaver libXtst >/dev/null ;;
    *" suse "*|*" opensuse"*) zypper -q -n install libgtk-3-0 mozilla-nss libasound2 libgbm1 libXss1 libXtst6 >/dev/null ;;
    *" arch "*) pacman -S --noconfirm --needed -q gtk3 nss alsa-lib mesa libxss libxtst >/dev/null ;;
  esac
fi

id tester >/dev/null 2>&1 || useradd -m tester
mkdir -p /etc/sudoers.d && echo 'tester ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tester

echo "--- install.sh"
INSTALLER="$HERE/install.sh"
if [ -n "${ISLET_INSTALLER_URL:-}" ]; then
  # Igual que un usuario: curl … | bash con el install.sh publicado en GitHub.
  INSTALLER=/tmp/install-remote.sh
  curl -fsSL "$ISLET_INSTALLER_URL" -o "$INSTALLER" && chmod 755 "$INSTALLER"
fi
sudo -u tester env ISLET_LOCAL_DIR="${ISLET_LOCAL_DIR:-}" GITHUB_TOKEN="${GITHUB_TOKEN:-}" PATH="/home/tester/.local/bin:$PATH" \
  bash "$INSTALLER" $MODE_ARG 2>&1 | grep -vE '^\s*#|%' | tail -4
[ "${PIPESTATUS[0]}" = 0 ] || { echo "FALLO: install.sh terminó con error"; exit 1; }

BIN=$(sudo -u tester env PATH="/home/tester/.local/bin:$PATH" sh -c 'command -v islet' || true)
[ -n "$BIN" ] || { echo "FALLO: no se encontró el comando islet"; exit 1; }
echo "binario: $BIN"

# Reproductor falso: usa el Node embebido de Electron y el dbus-next empaquetado en la app.
ASAR=$(find /opt /usr/lib /home/tester/.local -name app.asar -path '*slet*' 2>/dev/null | head -n1 || true)
ELECTRON_BIN=$(dirname "$(dirname "$ASAR")")/islet

echo "--- arranque"
cat > /tmp/run-islet.sh <<RUN
set -u
if [ -n "$ASAR" ]; then
  ELECTRON_RUN_AS_NODE=1 NODE_PATH="$ASAR/node_modules" "$ELECTRON_BIN" "$HERE/tools/fake-player.cjs" &
  sleep 2
fi
islet --no-sandbox > /tmp/islet.log 2>&1 &
PID=\$!
sleep 15
if ! kill -0 \$PID 2>/dev/null; then echo "FALLO: islet terminó al arrancar"; cat /tmp/islet.log; exit 1; fi
xwininfo -root -tree | grep -q '"Islet"' || { echo "FALLO: no hay ventana Islet"; cat /tmp/islet.log; exit 1; }
echo "ventana Islet: OK"
if [ -n "$ASAR" ]; then
  grep -q 'Fake Player: Midnight City' /tmp/islet.log || { echo "FALLO: no leyó el reproductor MPRIS"; cat /tmp/islet.log; exit 1; }
  echo "MPRIS: OK (\$(grep -m1 'Fake Player' /tmp/islet.log))"
fi
kill \$PID
RUN
chmod 755 /tmp/run-islet.sh
sudo -u tester env PATH="/home/tester/.local/bin:$PATH" HOME=/home/tester \
  dbus-run-session -- xvfb-run -a -s '-screen 0 1920x1080x24' bash /tmp/run-islet.sh

echo "--- desinstalación"
sudo -u tester env PATH="/home/tester/.local/bin:$PATH" bash "$HERE/install.sh" --uninstall | tail -1
sudo -u tester env PATH="/home/tester/.local/bin:$PATH" sh -c 'command -v islet' && { echo "FALLO: sigue instalado"; exit 1; }
echo "### OK: $PRETTY_NAME ${MODE_ARG}"
