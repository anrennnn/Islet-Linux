# Islet

Isla dinámica (estilo iPhone) para el escritorio Linux, con controles multimedia.
Hecha con **Electron + React** y conectada a cualquier reproductor mediante **MPRIS (D-Bus)**:
Spotify, VLC, Firefox, Chrome/Chromium, Rhythmbox, Elisa, Lollypop, mpv (con `mpv-mpris`), etc.

<p align="center">
  <img src="docs/compact.png" alt="Islet compacta" width="360"><br>
  <img src="docs/expanded.png" alt="Islet expandida" width="360">
</p>

## Instalación

### Automática (cualquier distro)

```bash
curl -fsSL https://raw.githubusercontent.com/anrennnn/Islet-Linux/main/install.sh | bash
```

El script detecta tu distro y arquitectura (x86_64 / ARM64), descarga el paquete correcto de la
[última release](https://github.com/anrennnn/Islet-Linux/releases/latest) y lo instala.
Usa `--appimage` para instalar sin root y `--uninstall` para quitarlo:

```bash
curl -fsSL https://raw.githubusercontent.com/anrennnn/Islet-Linux/main/install.sh | bash -s -- --appimage
```

### Manual, según tu distro

Descarga el archivo de [Releases](https://github.com/anrennnn/Islet-Linux/releases/latest) y:

| Distro | Archivo | Comando |
|---|---|---|
| Ubuntu, Debian, Linux Mint, Pop!_OS, Zorin, elementary | `islet-*-amd64.deb` / `arm64.deb` | `sudo apt install ./islet-*.deb` |
| Fedora, Nobara, RHEL, Rocky, AlmaLinux | `islet-*-x86_64.rpm` / `aarch64.rpm` | `sudo dnf install ./islet-*.rpm` |
| openSUSE Tumbleweed / Leap | `islet-*.rpm` | `sudo zypper install --allow-unsigned-rpm ./islet-*.rpm` |
| Arch, Manjaro, EndeavourOS, CachyOS, Garuda | `islet-*.pacman` | `sudo pacman -U ./islet-*.pacman` |
| Cualquier otra (Solus, Void, Gentoo, Slackware…) | `islet-*.AppImage` | `chmod +x islet-*.AppImage && ./islet-*.AppImage` |
| Sin FUSE / instalación portable | `islet-*.tar.gz` | `tar xf islet-*.tar.gz && ./islet-*/islet` |

> **NixOS:** usa `appimage-run islet-*.AppImage`.
> **AppImage** necesita FUSE 2 (`libfuse2` en Ubuntu, `fuse2` en Arch, `fuse-libs` en Fedora).

## Qué hace

- **Reposo:** píldora pequeña con la hora.
- **Compacta:** carátula + título + ecualizador animado mientras suena algo.
- **Expandida** (al pasar el ratón o al cambiar de canción): carátula, título, artista,
  reproductor, barra de progreso con *seek* y botones anterior / play-pausa / siguiente.
- Elige sola el reproductor que está sonando; desde la bandeja puedes fijar uno.
- Bandeja: reproductor, pantalla (multi-monitor), tema (oscuro / claro / cristal),
  iniciar con el sistema, salir.
- Fuera de la isla los clics pasan a las ventanas de debajo.

## Compatibilidad

| Entorno | Estado |
|---|---|
| X11 (GNOME, KDE, XFCE, Cinnamon, MATE, i3…) | Completo |
| Wayland (GNOME, KDE Plasma, Hyprland, Sway…) | Vía XWayland (se activa automáticamente) |
| Arquitecturas | x86_64 y ARM64 |

Necesitas un compositor para la transparencia (todos los escritorios modernos lo traen; en i3/bspwm
usa `picom`). En GNOME, el icono de bandeja requiere la extensión *AppIndicator*.

## Desarrollo

```bash
npm install
npm run dev                  # Vite + Electron con recarga
node tools/fake-player.cjs   # reproductor MPRIS falso para probar sin Spotify
```

## Publicar una versión

```bash
npm version patch            # o minor / major
git push origin main --tags   # o: Actions → Release → Run workflow
```

La acción [`release.yml`](.github/workflows/release.yml) compila `.AppImage`, `.deb`, `.rpm`,
`.pacman` y `.tar.gz` para x86_64 y ARM64, genera `SHA256SUMS.txt` y publica la release con
`install.sh`. [`ci.yml`](.github/workflows/ci.yml) compila y prueba MPRIS en cada push.

## Estructura

```
electron/main.cjs      ventana, bandeja, autoarranque, Wayland→XWayland
electron/mpris.cjs     cliente MPRIS por D-Bus (estado, carátulas, comandos)
electron/preload.cjs   puente seguro hacia React
src/Island.tsx         la isla (reposo / compacta / expandida)
src/styles.css         animaciones y temas
install.sh             instalador que detecta la distro
tools/                 reproductor de prueba y test MPRIS
```

## Licencia

MIT
