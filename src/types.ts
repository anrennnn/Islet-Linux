export type Status = 'Playing' | 'Paused' | 'Stopped'

export interface Track {
  id: string
  name: string
  status: Status
  title: string
  artist: string
  album: string
  art: string | null
  trackId: string | null
  length: number
  position: number
  canControl: boolean
}

export interface MediaState {
  active: Track | null
  players: { id: string; name: string; status: Status }[]
}

export type Theme = 'dark' | 'light' | 'glass'
export type Command = 'playPause' | 'next' | 'previous' | 'seek' | 'select'

declare global {
  interface Window {
    edge?: {
      onMedia: (cb: (s: MediaState) => void) => () => void
      onTheme: (cb: (t: Theme) => void) => () => void
      getConfig: () => Promise<{ theme: Theme }>
      command: (cmd: Command, arg?: unknown) => Promise<void>
      setShape: (r: { x: number; y: number; width: number; height: number; radius: number }) => void
      openMenu: () => void
    }
  }
}
