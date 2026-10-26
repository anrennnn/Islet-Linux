#!/usr/bin/env bash
# Prueba de instalación de extremo a extremo dentro de un contenedor de la distro (como root).
#   bash tests/install-test.sh            → instala con install.sh (paquete de la distro)
#   bash tests/install-test.sh --portable → instalación sin root (.tar.gz)
# Paquetes: ISLET_LOCAL_DIR=<carpeta> o, si no, la última release (ISLET_INSTALLER_URL para
# usar el install.sh publicado). Comprueba: install.sh termina bien, el comando existe, la app
# arranca, crea su ventana, lee un reproductor MPRIS de prueba y se desinstala limpia.
set -euo pipefail
MODE_ARG="${1:-}"
HERE=$(cd "$(dirname "$0")/.." && pwd)
. /etc/os-release; ID_LIKE="${ID_LIKE:-}"
echo "### $PRETTY_NAME ($(uname -m)) ${MODE_ARG}"

# Herramientas del entorno de prueba (no de Islet): curl, sudo, X virtual, D-Bus.
case " $ID $ID_LIKE " in
  *" debian "*|*" ubuntu "*)
    export DEBIAN_FRONTEND=noninteractive
    apt-get -qq update && apt-get -qq install -y curl ca-certificates sudo xvfb xauth x11-utils dbus dbus-x11 procps >/dev/null ;;
  *" fedora "*|*" rhel "*)
    dnf -q -y install curl tar gzip sudo xorg-x11-server-Xvfb xorg-x11-xauth xwininfo dbus-daemon dbus-tools which findutils procps-ng >/dev/null ;;
  *" suse "*|*" opensuse"*)
    zypper -q -n install curl sudo xvfb-run xwininfo /usr/bin/dbus-daemon which findutils procps tar gzip gawk >/dev/null ;;
  *" arch "*)
    pacman -Syu --noconfirm --needed -q curl sudo xorg-server-xvfb xorg-xauth xorg-xwininfo dbus which findutils procps-ng >/dev/null ;;
esac

# La versión portable usa el Python+GTK del sistema, como tendría un escritorio real.
if [ "$MODE_ARG" = --portable ]; then
  case " $ID $ID_LIKE " in
    *" debian "*|*" ubuntu "*) apt-get -qq install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 >/dev/null ;;
    *" fedora "*) dnf -q -y install python3-gobject gtk3 >/dev/null ;;
    *" suse "*|*" opensuse"*) zypper -q -n install python3-gobject python3-gobject-cairo typelib-1_0-Gtk-3_0 >/dev/null ;;
    *" arch "*) pacman -S --noconfirm --needed -q python-gobject python-cairo gtk3 >/dev/null ;;
  esac
fi

id tester >/dev/null 2>&1 || useradd -m tester
mkdir -p /etc/sudoers.d && echo 'tester ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tester
AS_TESTER=(sudo -u tester env HOME=/home/tester PATH="/home/tester/.local/bin:$PATH")

echo "--- install.sh"
INSTALLER="$HERE/install.sh"
if [ -n "${ISLET_INSTALLER_URL:-}" ]; then
  # Igual que un usuario: el install.sh publicado en GitHub.
  INSTALLER=/tmp/install-remote.sh
  curl -fsSL "$ISLET_INSTALLER_URL" -o "$INSTALLER" && chmod 755 "$INSTALLER"
fi
"${AS_TESTER[@]}" ISLET_LOCAL_DIR="${ISLET_LOCAL_DIR:-}" GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
  bash "$INSTALLER" $MODE_ARG 2>&1 | grep -vE '^\s*#|%' | tail -4
[ "${PIPESTATUS[0]}" = 0 ] || { echo "FALLO: install.sh terminó con error"; exit 1; }

BIN=$("${AS_TESTER[@]}" sh -c 'command -v islet' || true)
[ -n "$BIN" ] || { echo "FALLO: no se encontró el comando islet"; exit 1; }
echo "binario: $BIN ($("${AS_TESTER[@]}" islet --version))"

echo "--- arranque"
cat > /tmp/run-islet.sh <<RUN
set -u
python3 "$HERE/tools/fake_player.py" &
sleep 2
islet > /tmp/islet.log 2>&1 &
PID=\$!
sleep 8
if ! kill -0 \$PID 2>/dev/null; then echo "FALLO: islet terminó al arrancar"; cat /tmp/islet.log; exit 1; fi
xwininfo -root -tree | grep -q '"Islet": ("islet" "Islet")' || { echo "FALLO: no hay ventana Islet"; cat /tmp/islet.log; exit 1; }
echo "ventana Islet: OK"
grep -q 'Fake Player: Midnight City' /tmp/islet.log || { echo "FALLO: no leyó el reproductor MPRIS"; cat /tmp/islet.log; exit 1; }
echo "MPRIS: OK (\$(grep -m1 'Fake Player' /tmp/islet.log))"
echo "memoria: \$(ps -o rss= -p \$PID | awk '{printf "%.0f MB", \$1/1024}')"
kill \$PID \$(jobs -p) 2>/dev/null
RUN
chmod 755 /tmp/run-islet.sh
# openSUSE no trae dbus-run-session: en ese caso levantamos un bus de sesión a mano.
if command -v dbus-run-session >/dev/null; then
  "${AS_TESTER[@]}" dbus-run-session -- xvfb-run -a -s '-screen 0 1920x1080x24' bash /tmp/run-islet.sh
else
  "${AS_TESTER[@]}" bash -c '
    export DBUS_SESSION_BUS_ADDRESS=$(dbus-daemon --session --fork --print-address)
    xvfb-run -a -s "-screen 0 1920x1080x24" bash /tmp/run-islet.sh'
fi

echo "--- desinstalación"
"${AS_TESTER[@]}" bash "$HERE/install.sh" --uninstall | tail -1
"${AS_TESTER[@]}" sh -c 'command -v islet' && { echo "FALLO: sigue instalado"; exit 1; }
echo "### OK: $PRETTY_NAME ${MODE_ARG}"
