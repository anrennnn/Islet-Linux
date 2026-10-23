// Cliente MPRIS (org.mpris.MediaPlayer2) sobre D-Bus.
// Funciona con Spotify, VLC, Firefox, Chromium, Rhythmbox, mpv (mpv-mpris), Elisa, etc.
const { EventEmitter } = require('node:events')
const fs = require('node:fs')
const path = require('node:path')
const dbus = require('dbus-next')

const MPRIS_PREFIX = 'org.mpris.MediaPlayer2.'
const MPRIS_PATH = '/org/mpris/MediaPlayer2'
const PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player'
const ROOT_IFACE = 'org.mpris.MediaPlayer2'
const PROPS_IFACE = 'org.freedesktop.DBus.Properties'

const unwrap = (v) => (v instanceof dbus.Variant ? unwrap(v.value) : v)
const toNum = (v) => (typeof v === 'bigint' ? Number(v) : Number(v ?? 0))

const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif' }

// El renderer no puede leer file:// directamente, así que convertimos a data: URL.
function resolveArt(url) {
  if (!url) return null
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) return url
  if (url.startsWith('file://')) {
    try {
      const file = decodeURIComponent(new URL(url).pathname)
      const buf = fs.readFileSync(file)
      if (buf.length > 8 * 1024 * 1024) return null
      const mime = MIME[path.extname(file).toLowerCase()] || 'image/png'
      return `data:${mime};base64,${buf.toString('base64')}`
    } catch {
      return null
    }
  }
  return null
}

// dbus-next solo habla con sockets "abstract" a través del módulo nativo usocket, que no
// empaquetamos. Node sí los soporta con una ruta que empieza por \0, así que reescribimos
// la dirección (Ubuntu 22.04, sesiones sin systemd, dbus-run-session antiguos…).
function sessionBusAddress(address = process.env.DBUS_SESSION_BUS_ADDRESS || '') {
  const parts = address.split(';').filter(Boolean).map((entry) => {
    const m = entry.match(/^unix:(?:.*,)?abstract=([^,]+)/)
    return m ? `unix:path=\0${decodeURIComponent(m[1])}` : entry
  })
  if (parts.length) return parts.join(';')
  const runtime = process.env.XDG_RUNTIME_DIR || `/run/user/${process.getuid?.()}`
  return fs.existsSync(`${runtime}/bus`) ? `unix:path=${runtime}/bus` : undefined
}

class Player {
  constructor(busName, iface, props, identity) {
    this.busName = busName
    this.iface = iface
    this.props = props
    this.identity = identity
    this.status = 'Stopped'
    this.metadata = {}
    this.canControl = true
    this.position = 0
    this.positionAt = Date.now()
    this.lastActive = 0
    this.artCache = { url: null, resolved: null }
  }

  applyProps(changed) {
    if ('PlaybackStatus' in changed) {
      this.status = unwrap(changed.PlaybackStatus)
      if (this.status === 'Playing') this.lastActive = Date.now()
    }
    if ('Metadata' in changed) {
      const raw = unwrap(changed.Metadata) || {}
      const md = {}
      for (const [k, v] of Object.entries(raw)) md[k] = unwrap(v)
      this.metadata = md
      this.lastActive = Date.now()
      this.position = 0
      this.positionAt = Date.now()
    }
    if ('CanControl' in changed) this.canControl = !!unwrap(changed.CanControl)
    if ('Position' in changed) this.setPosition(toNum(unwrap(changed.Position)))
  }

  setPosition(us) {
    this.position = us
    this.positionAt = Date.now()
  }

  estimatedPosition() {
    const drift = this.status === 'Playing' ? (Date.now() - this.positionAt) * 1000 : 0
    return this.position + drift
  }

  snapshot() {
    const md = this.metadata
    const artUrl = md['mpris:artUrl'] || null
    if (artUrl !== this.artCache.url) this.artCache = { url: artUrl, resolved: resolveArt(artUrl) }
    const artist = md['xesam:artist']
    return {
      id: this.busName,
      name: this.identity || this.busName.slice(MPRIS_PREFIX.length).split('.')[0],
      status: this.status,
      title: md['xesam:title'] || '',
      artist: Array.isArray(artist) ? artist.join(', ') : artist || '',
      album: md['xesam:album'] || '',
      art: this.artCache.resolved,
      trackId: md['mpris:trackid'] || null,
      length: toNum(md['mpris:length']) / 1e6,
      position: this.estimatedPosition() / 1e6,
      canControl: this.canControl
    }
  }
}

class MprisWatcher extends EventEmitter {
  constructor() {
    super()
    this.players = new Map()
    this.pinned = null
  }

  async start() {
    this.bus = dbus.sessionBus({ busAddress: sessionBusAddress() })
    const obj = await this.bus.getProxyObject('org.freedesktop.DBus', '/org/freedesktop/DBus')
    this.dbusIface = obj.getInterface('org.freedesktop.DBus')
    this.dbusIface.on('NameOwnerChanged', (name, oldOwner, newOwner) => {
      if (!name.startsWith(MPRIS_PREFIX)) return
      if (newOwner) this.addPlayer(name)
      else this.removePlayer(name)
    })
    const names = await this.dbusIface.ListNames()
    await Promise.all(names.filter((n) => n.startsWith(MPRIS_PREFIX)).map((n) => this.addPlayer(n)))
    // Refresca la posición real cada pocos segundos para corregir la deriva.
    this.poll = setInterval(() => this.refreshPositions(), 3000)
    this.emitChange()
  }

  async addPlayer(busName) {
    if (this.players.has(busName)) return
    try {
      const obj = await this.bus.getProxyObject(busName, MPRIS_PATH)
      const iface = obj.getInterface(PLAYER_IFACE)
      const props = obj.getInterface(PROPS_IFACE)
      let identity = null
      try {
        identity = unwrap(await props.Get(ROOT_IFACE, 'Identity'))
      } catch {}
      const player = new Player(busName, iface, props, identity)
      player.applyProps(await props.GetAll(PLAYER_IFACE))
      props.on('PropertiesChanged', (ifaceName, changed) => {
        if (ifaceName !== PLAYER_IFACE) return
        player.applyProps(changed)
        this.emitChange()
      })
      iface.on('Seeked', (pos) => {
        player.setPosition(toNum(pos))
        this.emitChange()
      })
      this.players.set(busName, player)
      this.emitChange()
    } catch (err) {
      console.warn(`[mpris] no se pudo conectar con ${busName}:`, err.message)
    }
  }

  removePlayer(busName) {
    const p = this.players.get(busName)
    if (!p) return
    p.props.removeAllListeners()
    p.iface.removeAllListeners()
    this.players.delete(busName)
    if (this.pinned === busName) this.pinned = null
    this.emitChange()
  }

  async refreshPositions() {
    for (const p of this.players.values()) {
      if (p.status !== 'Playing') continue
      try {
        p.setPosition(toNum(unwrap(await p.props.Get(PLAYER_IFACE, 'Position'))))
      } catch {}
    }
  }

  // Prioridad: reproductor fijado > el que está sonando más reciente > el último activo.
  active() {
    if (this.pinned && this.players.has(this.pinned)) return this.players.get(this.pinned)
    const list = [...this.players.values()]
    const playing = list.filter((p) => p.status === 'Playing').sort((a, b) => b.lastActive - a.lastActive)
    if (playing.length) return playing[0]
    return list.sort((a, b) => b.lastActive - a.lastActive)[0] || null
  }

  state() {
    const active = this.active()
    return {
      active: active ? active.snapshot() : null,
      players: [...this.players.values()].map((p) => ({ id: p.busName, name: p.snapshot().name, status: p.status }))
    }
  }

  emitChange() {
    this.emit('change', this.state())
  }

  async command(cmd, arg) {
    if (cmd === 'select') {
      this.pinned = arg || null
      return this.emitChange()
    }
    const p = this.active()
    if (!p) return
    switch (cmd) {
      case 'playPause':
        return p.iface.PlayPause()
      case 'next':
        return p.iface.Next()
      case 'previous':
        return p.iface.Previous()
      case 'seek': {
        const trackId = p.metadata['mpris:trackid']
        if (!trackId) return
        const us = BigInt(Math.max(0, Math.round(Number(arg) * 1e6)))
        await p.iface.SetPosition(trackId, us)
        p.setPosition(Number(us))
        return this.emitChange()
      }
    }
  }

  stop() {
    clearInterval(this.poll)
    this.bus?.disconnect()
  }
}

module.exports = { MprisWatcher, sessionBusAddress }
