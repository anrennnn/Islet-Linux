const { app, BrowserWindow, ipcMain, screen, Tray, Menu, nativeImage } = require('electron')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { MprisWatcher } = require('./mpris.cjs')

// En Wayland las ventanas nativas no pueden posicionarse ni quedar "siempre encima",
// así que usamos XWayland. Chromium elige la plataforma antes de ejecutar este archivo,
// por lo que appendSwitch llega tarde: hay que relanzar el proceso con el flag.
// (Electron rellena ozone-platform=wayland por su cuenta, así que miramos argv: si el
// usuario pasó --ozone-platform explícitamente respetamos su elección.)
const isWayland = process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY
const userChosePlatform = process.argv.some((a) => a.startsWith('--ozone-platform'))
const needsXWayland =
  isWayland && !!process.env.DISPLAY && !userChosePlatform && app.commandLine.getSwitchValue('ozone-platform') !== 'x11'
if (needsXWayland) {
  // En AppImage execPath apunta al montaje temporal, que desaparece al salir.
  app.relaunch({
    execPath: process.env.APPIMAGE || process.execPath,
    args: [...process.argv.slice(1), '--ozone-platform=x11']
  })
  app.exit(0)
} else {
  start()
}

function start() {
  app.commandLine.appendSwitch('enable-transparent-visuals')

  if (!app.requestSingleInstanceLock()) return app.quit()

  // La ventana es más grande que la isla expandida; setShape() recorta la zona
  // clicable al rectángulo real de la isla para que el resto deje pasar los clics.
  const WIN_W = 480
  const WIN_H = 220
  const TOP_MARGIN = 8

  const configPath = path.join(app.getPath('userData'), 'config.json')
  const defaults = { displayId: null, theme: 'dark', firstRunDone: false }
  let config = { ...defaults }
  try {
    config = { ...defaults, ...JSON.parse(fs.readFileSync(configPath, 'utf8')) }
  } catch {}
  const saveConfig = () => {
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2))
  }

  let win = null
  let tray = null
  const mpris = new MprisWatcher()
  let lastState = { active: null, players: [] }

  function targetDisplay() {
    const all = screen.getAllDisplays()
    return all.find((d) => d.id === config.displayId) || screen.getPrimaryDisplay()
  }

  function placeWindow() {
    if (!win) return
    const { workArea } = targetDisplay()
    win.setBounds({
      x: Math.round(workArea.x + (workArea.width - WIN_W) / 2),
      y: workArea.y + TOP_MARGIN,
      width: WIN_W,
      height: WIN_H
    })
  }

  function createWindow() {
    win = new BrowserWindow({
      width: WIN_W,
      height: WIN_H,
      transparent: true,
      backgroundColor: '#00000000',
      frame: false,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      hasShadow: false,
      alwaysOnTop: true,
      focusable: true,
      show: false,
      // DOCK: los gestores de ventanas respetan su posición, no la decoran, no le dan
      // foco ni la ponen en la barra de tareas y la mantienen por encima de las normales.
      type: 'dock',
      webPreferences: {
        preload: path.join(__dirname, 'preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    })
    win.setAlwaysOnTop(true, 'screen-saver')
    win.setVisibleOnAllWorkspaces(true)
    placeWindow()

    if (process.env.VITE_DEV) win.loadURL('http://localhost:5173')
    else win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))

    win.once('ready-to-show', () => {
      win.showInactive()
      // Algunos gestores recolocan la ventana al mapearla; la devolvemos a su sitio.
      placeWindow()
      setTimeout(placeWindow, 500)
      win.webContents.send('media:state', lastState)
    })
    win.on('closed', () => (win = null))
  }

  const iconPath = () => path.join(__dirname, '..', 'build', 'icon.png')

  function autostartFile() {
    return path.join(os.homedir(), '.config', 'autostart', 'islet.desktop')
  }

  function setAutostart(enabled) {
    const file = autostartFile()
    if (!enabled) return fs.rmSync(file, { force: true })
    // ISLET_LAUNCHER lo define el lanzador de install.sh (lleva los flags necesarios);
    // en AppImage process.execPath apunta a un montaje temporal y APPIMAGE es la ruta real.
    const exec = process.env.ISLET_LAUNCHER || process.env.APPIMAGE || process.execPath
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(
      file,
      [
        '[Desktop Entry]',
        'Type=Application',
        'Name=Islet',
        `Exec="${exec}"${app.isPackaged ? '' : ` "${path.join(__dirname, '..')}"`}`,
        // Nombre del icono instalado por el paquete; la ruta dentro de app.asar no la ve el escritorio.
        `Icon=${app.isPackaged ? 'islet' : iconPath()}`,
        'X-GNOME-Autostart-enabled=true',
        'X-GNOME-Autostart-Delay=3',
        ''
      ].join('\n')
    )
  }

  // Mismo menú para la bandeja y para el clic derecho sobre la isla (GNOME no muestra
  // iconos de bandeja sin la extensión AppIndicator).
  function buildMenu() {
    const players = lastState.players
    const displays = screen.getAllDisplays()
    const current = targetDisplay().id
    return Menu.buildFromTemplate([
      { label: 'Islet', enabled: false },
      { type: 'separator' },
      {
        label: 'Reproductor',
        submenu: [
          { label: 'Automático', type: 'radio', checked: !mpris.pinned, click: () => mpris.command('select', null) },
          ...players.map((p) => ({
            label: `${p.name} (${p.status})`,
            type: 'radio',
            checked: mpris.pinned === p.id,
            click: () => mpris.command('select', p.id)
          }))
        ]
      },
      {
        label: 'Pantalla',
        submenu: displays.map((d, i) => ({
          label: `Pantalla ${i + 1} (${d.size.width}×${d.size.height})`,
          type: 'radio',
          checked: d.id === current,
          click: () => {
            config.displayId = d.id
            saveConfig()
            placeWindow()
          }
        }))
      },
      {
        label: 'Tema',
        submenu: ['dark', 'light', 'glass'].map((t) => ({
          label: { dark: 'Oscuro', light: 'Claro', glass: 'Cristal' }[t],
          type: 'radio',
          checked: config.theme === t,
          click: () => {
            config.theme = t
            saveConfig()
            win?.webContents.send('app:theme', t)
          }
        }))
      },
      {
        label: 'Iniciar con el sistema',
        type: 'checkbox',
        checked: fs.existsSync(autostartFile()),
        click: (item) => setAutostart(item.checked)
      },
      { type: 'separator' },
      { label: 'Salir', click: () => app.quit() }
    ])
  }

  function buildTrayMenu() {
    tray?.setContextMenu(buildMenu())
  }

  // Forma de la ventana = isla con esquinas redondeadas, aproximadas con una franja por
  // fila de píxeles. Sin compositor (i3, Openbox, VMs) esto es lo que se ve; con compositor
  // define la zona que recibe clics.
  function roundedShape({ x, y, width, height, radius }) {
    const r = Math.min(Math.floor(radius || 0), Math.floor(width / 2), Math.floor(height / 2))
    if (r <= 0) return [{ x, y, width, height }]
    const rects = [{ x, y: y + r, width, height: height - 2 * r }]
    for (let i = 0; i < r; i++) {
      const dy = r - i - 0.5
      const inset = Math.ceil(r - Math.sqrt(r * r - dy * dy))
      const w = width - 2 * inset
      rects.push({ x: x + inset, y: y + i, width: w, height: 1 })
      rects.push({ x: x + inset, y: y + height - 1 - i, width: w, height: 1 })
    }
    return rects
  }

  ipcMain.on('island:shape', (_e, rect) => {
    if (!win || !rect) return
    const x = Math.max(0, Math.floor(rect.x))
    const y = Math.max(0, Math.floor(rect.y))
    win.setShape(
      roundedShape({
        x,
        y,
        width: Math.min(WIN_W - x, Math.ceil(rect.width)),
        height: Math.min(WIN_H - y, Math.ceil(rect.height)),
        radius: rect.radius
      })
    )
  })

  ipcMain.on('island:menu', () => win && buildMenu().popup({ window: win }))
  ipcMain.handle('media:command', (_e, cmd, arg) => mpris.command(cmd, arg).catch((err) => console.warn(err.message)))
  ipcMain.handle('app:config', () => config)

  app.whenReady().then(async () => {
    let lastLogged = ''
    mpris.on('change', (state) => {
      const a = state.active
      const line = a ? `${a.name}: ${a.title} — ${a.artist} (${a.status})` : 'sin reproductor'
      if (line !== lastLogged) console.log(`[islet] ${(lastLogged = line)}`)
      const playersChanged = JSON.stringify(state.players) !== JSON.stringify(lastState.players)
      lastState = state
      win?.webContents.send('media:state', state)
      if (playersChanged) buildTrayMenu()
    })
    try {
      await mpris.start()
    } catch (err) {
      console.error('[mpris] no hay bus de sesión D-Bus:', err.message)
    }

    // La primera vez que se abre la versión instalada, se activa el inicio automático
    // (se puede quitar desde el menú de la isla o de la bandeja).
    if (!config.firstRunDone) {
      if (app.isPackaged) {
        try {
          setAutostart(true)
        } catch (err) {
          console.warn('[autostart]', err.message)
        }
      }
      config.firstRunDone = true
      saveConfig()
    }

    // Los visuales transparentes en Linux necesitan que el compositor esté listo.
    setTimeout(createWindow, process.platform === 'linux' ? 300 : 0)

    try {
      tray = new Tray(nativeImage.createFromPath(iconPath()).resize({ width: 22, height: 22 }))
      tray.setToolTip('Islet')
      buildTrayMenu()
    } catch (err) {
      console.warn('[tray] no disponible en este escritorio:', err.message)
    }

    screen.on('display-added', () => (placeWindow(), buildTrayMenu()))
    screen.on('display-removed', () => (placeWindow(), buildTrayMenu()))
    screen.on('display-metrics-changed', placeWindow)
  })

  app.on('second-instance', () => win?.showInactive())
  app.on('window-all-closed', () => {})
  app.on('before-quit', () => mpris.stop())
}
