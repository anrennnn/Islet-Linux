#!/usr/bin/env bash
# Prueba de interacción en un escritorio X11 real (Openbox): con un reproductor MPRIS falso,
# pasa el ratón por la isla, pulsa play/pausa y siguiente, y comprueba que el reproductor
# responde. Guarda capturas en $SHOTS (por defecto /tmp/islet-shots).
# Requiere: islet instalado (o ISLET_CMD), Xvfb, un gestor de ventanas (WM, por defecto openbox),
# xdotool, ImageMagick (import), dbus y python3-gi.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
SHOTS=${SHOTS:-/tmp/islet-shots}; mkdir -p "$SHOTS"
ISLET_CMD=${ISLET_CMD:-islet}
WM=${WM:-openbox}
LOG=/tmp/islet-interaction.log
# Cierra Xvfb, Openbox, el reproductor e Islet al terminar (Islet es de instancia única).
trap 'kill $(jobs -p) 2>/dev/null; sleep 1' EXIT

Xvfb :7 -screen 0 1920x1080x24 >/dev/null 2>&1 &
export DISPLAY=:7; sleep 2
$WM >/dev/null 2>&1 & sleep 1
command -v xsetroot >/dev/null && xsetroot -solid "#7a8ca5"   # fondo visible en las capturas
python3 "$HERE/tools/fake_player.py" &
sleep 2
$ISLET_CMD >"$LOG" 2>&1 &
sleep 10   # deja pasar el "peek" inicial de 3,5 s

fail() { echo "FALLO: $*"; tail -20 "$LOG"; exit 1; }
wait_log() { for _ in $(seq 1 20); do grep -q "$1" "$LOG" && return 0; sleep 0.5; done; return 1; }

W=$(xwininfo -root -tree | grep '"Islet": ("islet"' | grep -E ' [0-9]{3}x[0-9]{3}' | awk '{print $1}' | head -1)
[ -n "$W" ] || fail "no hay ventana"
eval "$(xwininfo -id "$W" | awk '/Absolute upper-left X/{print "WX="$4} /Absolute upper-left Y/{print "WY="$4} /Width/{print "WW="$2}')"
CX=$((WX + WW / 2))
echo "ventana en ${WX},${WY}; centro x=${CX}"
import -window root -crop 600x220+$((CX - 300))+0 "$SHOTS/1-compacta.png"

xdotool mousemove "$CX" $((WY + 18)); sleep 1.2
import -window root -crop 600x220+$((CX - 300))+0 "$SHOTS/2-expandida.png"

# Fila de controles: 12 px de margen inferior + 18 px (mitad del botón de 36 px).
BY=$((WY + 168 - 12 - 18))
xdotool mousemove "$CX" "$BY" click 1
wait_log 'Midnight City — M83 (Paused)' || fail "play/pausa no pausó"
echo "play/pausa: OK"
xdotool mousemove $((CX + 58)) "$BY" click 1
wait_log 'Blinding Lights — The Weeknd' || fail "siguiente no cambió de canción"
echo "siguiente: OK"
sleep 1
import -window root -crop 600x220+$((CX - 300))+0 "$SHOTS/3-siguiente.png"
xdotool mousemove $((CX - 58)) "$BY" click 1
wait_log 'Fake Player: Midnight City — M83 (Paused)' || fail "anterior no volvió a la canción"
echo "anterior: OK"

# Al salir el ratón la isla vuelve a la píldora y deja pasar los clics fuera de ella.
xdotool mousemove 100 600; sleep 4.5   # incluye el "peek" de 3,5 s tras cambiar de canción
import -window root -crop 600x220+$((CX - 300))+0 "$SHOTS/4-recogida.png"
echo "### OK: interacción"
