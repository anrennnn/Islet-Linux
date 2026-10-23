import { useEffect, useState } from 'react'
import type { MediaState, Theme, Track } from './types'

// Datos de ejemplo para abrir la UI en un navegador sin Electron (npm run vite).
const demo: MediaState = {
  active: {
    id: 'demo', name: 'Demo', status: 'Playing', title: 'Midnight City', artist: 'M83',
    album: 'Hurry Up, We\'re Dreaming', art: null, trackId: '/demo', length: 244, position: 42, canControl: true
  },
  players: [{ id: 'demo', name: 'Demo', status: 'Playing' }]
}

export function useMedia() {
  const [state, setState] = useState<MediaState>(window.edge ? { active: null, players: [] } : demo)
  const [receivedAt, setReceivedAt] = useState(() => Date.now())

  useEffect(() => {
    if (!window.edge) return
    return window.edge.onMedia((s) => {
      setState(s)
      setReceivedAt(Date.now())
    })
  }, [])

  return { state, receivedAt }
}

// Posición interpolada localmente para que la barra avance suave entre eventos D-Bus.
export function usePosition(track: Track | null, receivedAt: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (track?.status !== 'Playing') return
    const t = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(t)
  }, [track?.status])
  if (!track) return 0
  const elapsed = track.status === 'Playing' ? Math.max(0, now - receivedAt) / 1000 : 0
  const pos = track.position + elapsed
  return track.length > 0 ? Math.min(pos, track.length) : pos
}

export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>('dark')
  useEffect(() => {
    if (!window.edge) return
    window.edge.getConfig().then((c) => setTheme(c.theme))
    return window.edge.onTheme(setTheme)
  }, [])
  return theme
}
