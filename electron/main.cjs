const { app, BrowserWindow, ipcMain, screen, Tray, Menu, nativeImage } = require('electron')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { MprisWatcher } = require('./mpris.cjs')

// En Wayland las ventanas nativas no pueden posicionarse ni quedar "siempre encima",
// así que usamos XWayland salvo que el usuario fuerce otra cosa con --ozone-platform.
const isWayland = process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY
if (isWayland && !app.commandLine.hasSwitch('ozone-platform')) {
  app.commandLine.appendSwitch('ozone-platform', 'x11')
}
app.commandLine.appendSwitch('enable-transparent-visuals')

if (!app.requestSingleInstanceLock()) app.quit()

// La ventana es más grande que la isla expandida; setShape() recorta la zona
// clicable al rectángulo real de la isla para que el resto deje pasar los clics.
const WIN_W = 480
const WIN_H = 220
const TOP_MARGIN = 8

const configPath = path.join(app.getPath('userData'), 'config.json')
const defaults = { displayId: null, theme: 'dark' }
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
    type: 'toolbar',
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
  // En AppImage process.execPath apunta a un montaje temporal; APPIMAGE es la ruta real.
  const exec = process.env.APPIMAGE || process.execPath
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(
    file,
    [
      '[Desktop Entry]',
      'Type=Application',
      'Name=Islet',
      `Exec="${exec}"${app.isPackaged ? '' : ` "${path.join(__dirname, '..')}"`}`,
      `Icon=${iconPath()}`,
      'X-GNOME-Autostart-enabled=true',
      'X-GNOME-Autostart-Delay=3',
      ''
    ].join('\n')
  )
}

function buildTrayMenu() {
  if (!tray) return
  const players = lastState.players
  const displays = screen.getAllDisplays()
  const current = targetDisplay().id
  tray.setContextMenu(
    Menu.buildFromTemplate([
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
  )
}

ipcMain.on('island:shape', (_e, rect) => {
  if (!win || !rect) return
  const r = {
    x: Math.max(0, Math.floor(rect.x)),
    y: Math.max(0, Math.floor(rect.y)),
    width: Math.min(WIN_W, Math.ceil(rect.width)),
    height: Math.min(WIN_H, Math.ceil(rect.height))
  }
  win.setShape([r])
})

ipcMain.handle('media:command', (_e, cmd, arg) => mpris.command(cmd, arg).catch((err) => console.warn(err.message)))
ipcMain.handle('app:config', () => config)

app.whenReady().then(async () => {
  mpris.on('change', (state) => {
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
