#!/usr/bin/env bash
# Prueba Islet dentro de un escritorio real, en un contenedor Ubuntu 24.04 (como root):
#   bash tests/desktop-test.sh xfwm4     → XFCE (sin compositor) + prueba de interacción con ratón
#   bash tests/desktop-test.sh xfwm4-composite → XFCE con compositor (transparencia real)
#   bash tests/desktop-test.sh openbox   → X11 + prueba de interacción con ratón
#   bash tests/desktop-test.sh mutter    → GNOME (Mutter) en Wayland
#   bash tests/desktop-test.sh kwin      → KDE Plasma (KWin) en Wayland
# Comprueba que la ventana queda arriba al centro, tipo DOCK, siempre encima y, en Wayland,
# que la app usa XWayland. Instala el .deb de ISLET_LOCAL_DIR.
set -euo pipefail
WM=$1
HERE=$(cd "$(dirname "$0")/.." && pwd)
export DEBIAN_FRONTEND=noninteractive
case $WM in
  openbox|xfwm4|xfwm4-composite) PKGS="openbox xfwm4 xvfb xdotool imagemagick x11-xserver-utils" ;;
  mutter) PKGS="mutter xwayland" ;;
  kwin) PKGS="kwin-wayland xwayland" ;;
esac
echo "### escritorio: $WM"
apt-get -qq update
apt-get -qq install -y --no-install-recommends $PKGS x11-utils dbus dbus-x11 xauth \
  "$(ls "$ISLET_LOCAL_DIR"/*_all.deb | head -1)" >/dev/null
mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix
id tester >/dev/null 2>&1 || useradd -m tester
install -d -o tester -m 700 /tmp/xdg

case $WM in
  openbox|xfwm4) WMCMD=$WM ;;
  xfwm4-composite) WMCMD="xfwm4 --compositor=on" ;;
  *) WMCMD="" ;;
esac
if [ -n "$WMCMD" ]; then
  mkdir -p "/tmp/islet-shots/$WM" && chmod -R 777 /tmp/islet-shots
  su tester -c "WM='$WMCMD' SHOTS=/tmp/islet-shots/$WM dbus-run-session -- bash $HERE/tests/interaction-test.sh"
fi

cat > /tmp/desktop-run.sh <<IN
set -u
WMCMD="$WMCMD"
export XDG_RUNTIME_DIR=/tmp/xdg XWAYLAND_NO_GLAMOR=1 LIBGL_ALWAYS_SOFTWARE=1
case $WM in
  mutter) mutter --wayland --headless --virtual-monitor 1920x1080 >/tmp/wm.log 2>&1 & ;;
  # kwin_wayland tiene capabilities de archivo que un contenedor no permite: usamos una copia.
  kwin)   cp /usr/bin/kwin_wayland /tmp/kwin_wayland
          /tmp/kwin_wayland --virtual --width 1920 --height 1080 --xwayland >/tmp/wm.log 2>&1 & ;;
  *) Xvfb :9 -screen 0 1920x1080x24 >/dev/null 2>&1 & sleep 2; export DISPLAY=:9; \$WMCMD >/dev/null 2>&1 & ;;
esac
sleep 6
IN
cat >> /tmp/desktop-run.sh <<'IN'
trap 'kill $(jobs -p) 2>/dev/null' EXIT
if [ -z "${DISPLAY:-}" ]; then
  export WAYLAND_DISPLAY=wayland-0 XDG_SESSION_TYPE=wayland
  for _ in $(seq 1 15); do D=$(ls /tmp/.X11-unix | sed 's/X/:/' | head -1); [ -n "$D" ] && break; sleep 1; done
  export DISPLAY=$D
  A=$(ls $XDG_RUNTIME_DIR/.mutter-Xwaylandauth.* $XDG_RUNTIME_DIR/xauth_* 2>/dev/null | head -1)
  [ -n "$A" ] && export XAUTHORITY=$A
fi
islet >/tmp/islet.log 2>&1 &
sleep 14
fail() { echo "FALLO: $*"; tail -15 /tmp/islet.log; tail -5 /tmp/wm.log 2>/dev/null; exit 1; }
W=$(timeout 10 xwininfo -root -tree | grep '"Islet": ("islet"' | grep -E ' [0-9]{3}x[0-9]{3}' | awk '{print $1}' | head -1)
[ -n "$W" ] || fail "no hay ventana Islet en X11/XWayland"
X=$(xwininfo -id $W | awk '/Absolute upper-left X/{print $4}')
Y=$(xwininfo -id $W | awk '/Absolute upper-left Y/{print $4}')
WW=$(xwininfo -id $W | awk '/Width/{print $2}')
PROPS=$(xprop -id $W _NET_WM_WINDOW_TYPE _NET_WM_STATE)
echo "posición ${X},${Y} ancho ${WW}"; echo "$PROPS"
[ $((X + WW / 2)) -ge 950 ] && [ $((X + WW / 2)) -le 970 ] || fail "no está centrada"
[ "$Y" -le 60 ] || fail "no está arriba"
echo "$PROPS" | grep -q DOCK || fail "no es de tipo DOCK"
echo "$PROPS" | grep -q ABOVE || fail "no está siempre encima"
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
  # La ventana solo aparece en el árbol X11 si la app eligió XWayland (GDK_BACKEND=x11).
  echo "usa XWayland: OK"
fi
echo "### OK: $1"
IN
su tester -c "dbus-run-session -- bash /tmp/desktop-run.sh $WM"
