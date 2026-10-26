# Islet

Isla dinámica (estilo iPhone) para el escritorio Linux, con controles multimedia.
Hecha con **Python + GTK 3** y conectada a cualquier reproductor mediante **MPRIS (D-Bus)**:
Spotify, VLC, Firefox, Chrome/Chromium, Rhythmbox, Parole, Audacious, Elisa, Lollypop,
mpv (con `mpv-mpris`), etc.

Es ligera (paquete `.deb` de ~32 KB, unos 35 MB de memoria) y está pensada para **XFCE**,
aunque funciona en GNOME, KDE Plasma, Cinnamon, MATE, LXQt, Openbox, i3…

<p align="center">
  <img src="docs/compact.png" alt="Islet compacta" width="300"><br>
  <img src="docs/expanded.png" alt="Islet expandida" width="440">
</p>

## Instalación

### Automática (cualquier distro)

```bash
curl -fsSL https://raw.githubusercontent.com/anrennnn/Islet-Linux/main/install.sh | bash
```

El script detecta tu distro, descarga el paquete correcto de la
[última release](https://github.com/anrennnn/Islet-Linux/releases/latest) y lo instala con tu
gestor de paquetes (que trae también Python y GTK si faltan). `--portable` instala sin root en
`~/.local` y `--uninstall` lo quita:

```bash
curl -fsSL https://raw.githubusercontent.com/anrennnn/Islet-Linux/main/install.sh | bash -s -- --portable
```

### Paquete .deb (Debian, Ubuntu, Xubuntu, Mint, Pop!_OS, MX Linux…)

Descarga `islet_<versión>_all.deb` de [Releases](https://github.com/anrennnn/Islet-Linux/releases/latest) y:

```bash
sudo apt install ./islet_*_all.deb
```

Es `Architecture: all`: el mismo paquete sirve para x86_64, ARM64 (Raspberry Pi) y cualquier otra.
Depende de `python3-gi`, `python3-gi-cairo` y `gir1.2-gtk-3.0`, que apt instala solo.

### Otras distros

| Distro | Archivo | Comando |
|---|---|---|
| Fedora, Nobara, RHEL, Rocky, AlmaLinux | `islet-*.noarch.rpm` | `sudo dnf install ./islet-*.rpm` |
| openSUSE Tumbleweed / Leap | `islet-*.noarch.rpm` | `sudo zypper install --allow-unsigned-rpm ./islet-*.rpm` |
| Arch, Manjaro, EndeavourOS, CachyOS | `islet-*-any.pkg.tar.zst` | `sudo pacman -U ./islet-*.pkg.tar.zst` |
| Cualquier otra (portable, sin root) | `islet-<versión>.tar.gz` | `tar xf islet-*.tar.gz && ./islet-*/islet.py` |

La versión portable usa el Python 3 + GTK 3 del sistema (`python3-gi`, `python3-gi-cairo`,
`gir1.2-gtk-3.0` o equivalentes); `install.sh --portable` comprueba que estén y te dice qué instalar.

## Qué hace

- **Reposo:** píldora pequeña con la hora.
- **Compacta:** carátula + título + ecualizador animado mientras suena algo.
- **Expandida** (al pasar el ratón o al cambiar de canción): carátula, título, artista,
  reproductor, barra de progreso con *seek* y botones anterior / play-pausa / siguiente.
- Elige sola el reproductor que está sonando; desde el menú puedes fijar uno.
- **Clic derecho sobre la isla** (o el icono de la bandeja): reproductor, pantalla
  (multi-monitor), tema (oscuro / claro / cristal), iniciar con el sistema y salir.
- Se inicia sola con el sistema desde la primera vez que la abres (se desactiva en el menú).
- Fuera de la isla los clics pasan a las ventanas de debajo; sin compositor conserva las
  esquinas redondeadas.

## Compatibilidad

| Entorno | Estado |
|---|---|
| XFCE (xfwm4 con o sin compositor) | Completo; bandeja con el complemento de área de notificación |
| X11 (Cinnamon, MATE, LXQt, Openbox, i3…) | Completo |
| Wayland (GNOME, KDE Plasma…) | Vía XWayland (`GDK_BACKEND=x11` automático) |

En GNOME el icono de bandeja requiere la extensión *AppIndicator*; sin ella usa el clic derecho
sobre la isla. Si `gir1.2-ayatanaappindicator3-0.1` está instalado se usa AppIndicator; si no,
el icono clásico de bandeja (XEmbed), que es el que muestra el panel de XFCE.

## Distros y escritorios probados

Cada release se instala con `install.sh` en contenedores de estas distros antes de publicarse
(y otra vez después, descargando la release real). La prueba arranca Islet en un X virtual,
comprueba que abre su ventana, que lee un reproductor MPRIS de prueba y que se desinstala limpio:

| Distro | Paquete | x86_64 | ARM64 |
|---|---|:-:|:-:|
| Ubuntu 24.04 / 22.04 | deb | ✓ | ✓ (24.04) |
| Debian 13 / 12 | deb | ✓ | ✓ (12) |
| Linux Mint 22 | deb | ✓ | |
| Fedora 42 / 41 | rpm | ✓ | ✓ (42) |
| openSUSE Tumbleweed / Leap 15.6 | rpm | ✓ | |
| Arch Linux, Manjaro | pacman | ✓ | |
| Ubuntu 24.04, Fedora 42 | portable (tar.gz) | ✓ | |

Además se prueba dentro de escritorios reales: **XFCE (xfwm4 con y sin compositor)**,
**Openbox**, y **GNOME (Mutter) y KDE Plasma (KWin) en Wayland**. Se comprueba que la isla queda
arriba al centro y siempre encima; en XFCE y Openbox una prueba mueve el ratón y pulsa
play/pausa, siguiente y anterior, verificando que el reproductor responde.

Ver [`install-tests.yml`](.github/workflows/install-tests.yml), [`tests/install-test.sh`](tests/install-test.sh),
[`tests/desktop-test.sh`](tests/desktop-test.sh) y [`tests/interaction-test.sh`](tests/interaction-test.sh).

## Desarrollo

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
tools/islet-dev                # ejecuta Islet desde el código
python3 tools/fake_player.py   # reproductor MPRIS falso para probar sin Spotify
dbus-run-session -- python3 tests/test_mpris.py
bash packaging/build.sh        # dist/islet_<v>_all.deb y dist/islet-<v>.tar.gz (+ rpm/pacman con fpm)
```

## Publicar una versión

Cambia `__version__` en `islet/__init__.py` y lanza **Actions → Release → Run workflow** (o
`git tag vX.Y.Z && git push origin vX.Y.Z`). La acción [`release.yml`](.github/workflows/release.yml)
construye `.deb`, `.rpm`, `.pkg.tar.zst` y `.tar.gz`, los prueba en todas las distros y escritorios
de arriba y solo si pasan publica la release con `SHA256SUMS.txt` e `install.sh`. Con *publish*
desmarcado solo construye y prueba.

## Estructura

```
islet/app.py          arranque, instancia única, menú, bandeja, XWayland
islet/island.py       la isla: ventana DOCK transparente dibujada con Cairo
islet/mpris.py        cliente MPRIS por D-Bus (Gio, asíncrono)
islet/config.py       configuración e inicio automático
packaging/            build.sh (deb, tar.gz, rpm, pacman) y lanzador
data/                 .desktop e iconos
install.sh            instalador que detecta la distro
tests/                pruebas de MPRIS, instalación, escritorios e interacción
tools/                reproductor de prueba y lanzador de desarrollo
```

## Licencia

MIT
