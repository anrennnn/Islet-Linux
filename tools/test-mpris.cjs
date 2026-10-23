// Prueba de humo del cliente MPRIS contra tools/fake-player.cjs.
const assert = require('node:assert')
const { MprisWatcher } = require('../electron/mpris.cjs')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const w = new MprisWatcher()
  let s
  w.on('change', (state) => (s = state))
  await w.start()
  await sleep(300)
  assert.equal(s.active?.title, 'Midnight City')
  assert.equal(s.active.status, 'Playing')
  await w.command('playPause')
  await sleep(200)
  assert.equal(s.active.status, 'Paused')
  await w.command('next')
  await sleep(200)
  assert.equal(s.active.title, 'Blinding Lights')
  await w.command('seek', 100)
  await sleep(200)
  assert.equal(Math.round(s.active.position), 100)
  console.log('MPRIS OK')
  w.stop()
  process.exit(0)
})().catch((err) => {
  console.error(err)
  process.exit(1)
})
