// Reproductor MPRIS falso para probar Islet sin Spotify/VLC.
// Uso: node tools/fake-player.cjs
const dbus = require('dbus-next')
const { Interface, ACCESS_READ } = dbus.interface
const { Variant } = dbus
const { sessionBusAddress } = require('../electron/mpris.cjs')

const tracks = [
  { title: 'Midnight City', artist: 'M83', length: 244 },
  { title: 'Blinding Lights', artist: 'The Weeknd', length: 200 }
]

class Player extends Interface {
  constructor() {
    super('org.mpris.MediaPlayer2.Player')
    this.i = 0
    this.status = 'Playing'
    this.pos = 0n
  }
  get PlaybackStatus() { return this.status }
  get CanControl() { return true }
  get Position() { return this.pos }
  get Metadata() {
    const t = tracks[this.i]
    return {
      'mpris:trackid': new Variant('o', `/fake/track/${this.i}`),
      'mpris:length': new Variant('x', BigInt(t.length * 1e6)),
      'xesam:title': new Variant('s', t.title),
      'xesam:artist': new Variant('as', [t.artist])
    }
  }
  PlayPause() { this.status = this.status === 'Playing' ? 'Paused' : 'Playing'; this.changed({ PlaybackStatus: this.status }) }
  Next() { this.i = (this.i + 1) % tracks.length; this.pos = 0n; this.changed({ Metadata: this.Metadata }) }
  Previous() { this.i = (this.i + tracks.length - 1) % tracks.length; this.pos = 0n; this.changed({ Metadata: this.Metadata }) }
  SetPosition(_id, pos) { this.pos = pos; this.Seeked(pos) }
  Seeked(pos) { return pos }
  changed(props) { Interface.emitPropertiesChanged(this, props, []) }
}
Player.configureMembers({
  properties: {
    PlaybackStatus: { signature: 's', access: ACCESS_READ },
    CanControl: { signature: 'b', access: ACCESS_READ },
    Position: { signature: 'x', access: ACCESS_READ },
    Metadata: { signature: 'a{sv}', access: ACCESS_READ }
  },
  methods: {
    PlayPause: {}, Next: {}, Previous: {},
    SetPosition: { inSignature: 'ox' }
  },
  signals: { Seeked: { signature: 'x' } }
})

class Root extends Interface {
  constructor() { super('org.mpris.MediaPlayer2') }
  get Identity() { return 'Fake Player' }
}
Root.configureMembers({ properties: { Identity: { signature: 's', access: ACCESS_READ } } })

;(async () => {
  const bus = dbus.sessionBus({ busAddress: sessionBusAddress() })
  await bus.requestName('org.mpris.MediaPlayer2.fakeplayer', 0)
  bus.export('/org/mpris/MediaPlayer2', new Player())
  bus.export('/org/mpris/MediaPlayer2', new Root())
  console.log('Fake MPRIS player listo')
})()
