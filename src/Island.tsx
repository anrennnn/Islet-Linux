import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useMedia, usePosition, useTheme } from './useMedia'
import type { Command, Track } from './types'

type Mode = 'idle' | 'compact' | 'expanded'

const fmt = (s: number) => {
  if (!isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60)
  return `${m}:${Math.floor(s % 60).toString().padStart(2, '0')}`
}

const send = (cmd: Command, arg?: unknown) => window.edge?.command(cmd, arg)

export function Island() {
  const { state, receivedAt } = useMedia()
  const theme = useTheme()
  const track = state.active && (state.active.title || state.active.status === 'Playing') ? state.active : null
  const [hover, setHover] = useState(false)
  const [peek, setPeek] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const leaveTimer = useRef<number>(undefined)

  // Al cambiar de canción la isla se abre unos segundos, como en iOS.
  const trackKey = track ? `${track.id}|${track.title}|${track.artist}` : ''
  useEffect(() => {
    if (!trackKey) return
    setPeek(true)
    const t = setTimeout(() => setPeek(false), 3500)
    return () => clearTimeout(t)
  }, [trackKey])

  const mode: Mode = !track ? 'idle' : hover || peek ? 'expanded' : 'compact'

  // Mantiene la zona clicable de la ventana igual al tamaño visible de la isla.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || !window.edge) return
    const report = () => {
      const r = el.getBoundingClientRect()
      const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0
      window.edge!.setShape({ x: r.x, y: r.y, width: r.width, height: r.height, radius })
    }
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    // El radio también se anima y no dispara ResizeObserver: recalculamos al terminar.
    el.addEventListener('transitionend', report)
    return () => {
      ro.disconnect()
      el.removeEventListener('transitionend', report)
    }
  }, [])

  const onEnter = () => {
    clearTimeout(leaveTimer.current)
    setHover(true)
  }
  const onLeave = () => {
    leaveTimer.current = window.setTimeout(() => setHover(false), 350)
  }

  return (
    <div className={`stage theme-${theme}`}>
      <div
        ref={ref}
        className={`island ${mode}`}
        onMouseEnter={onEnter}
        onMouseLeave={onLeave}
        onContextMenu={(e) => {
          e.preventDefault()
          window.edge?.openMenu()
        }}
      >
        {mode === 'idle' && <Clock />}
        {mode === 'compact' && track && <Compact track={track} />}
        {mode === 'expanded' && track && <Expanded track={track} receivedAt={receivedAt} />}
      </div>
    </div>
  )
}

function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 10_000)
    return () => clearInterval(t)
  }, [])
  return <span className="clock">{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
}

function Art({ track, size }: { track: Track; size: number }) {
  return track.art ? (
    <img className="art" src={track.art} width={size} height={size} alt="" draggable={false} />
  ) : (
    <div className="art art-fallback" style={{ width: size, height: size }}>♪</div>
  )
}

function Bars({ playing }: { playing: boolean }) {
  return (
    <div className={`bars ${playing ? 'on' : ''}`} aria-hidden>
      {[0, 1, 2, 3].map((i) => <i key={i} style={{ animationDelay: `${i * 0.13}s` }} />)}
    </div>
  )
}

function Compact({ track }: { track: Track }) {
  return (
    <div className="row compact-row">
      <Art track={track} size={24} />
      <span className="compact-title">{track.title || track.name}</span>
      <Bars playing={track.status === 'Playing'} />
    </div>
  )
}

function Expanded({ track, receivedAt }: { track: Track; receivedAt: number }) {
  const pos = usePosition(track, receivedAt)
  const pct = track.length > 0 ? (pos / track.length) * 100 : 0
  const playing = track.status === 'Playing'

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!track.length) return
    const r = e.currentTarget.getBoundingClientRect()
    send('seek', ((e.clientX - r.left) / r.width) * track.length)
  }

  return (
    <div className="expanded-body">
      <div className="row">
        <Art track={track} size={56} />
        <div className="meta">
          <div className="title" title={track.title}>{track.title || 'Sin título'}</div>
          <div className="artist" title={track.artist}>{track.artist || track.album || '—'}</div>
          <div className="source">{track.name}</div>
        </div>
        <Bars playing={playing} />
      </div>

      <div className="progress-row">
        <span>{fmt(pos)}</span>
        <div className={`progress ${track.length ? '' : 'disabled'}`} onClick={seek}>
          <div className="fill" style={{ width: `${pct}%` }} />
        </div>
        <span>{track.length ? fmt(track.length) : '--:--'}</span>
      </div>

      <div className="controls">
        <button onClick={() => send('previous')} aria-label="Anterior"><Icon d="M6 6h2v12H6zM9.5 12 18 18V6z" /></button>
        <button className="main" onClick={() => send('playPause')} aria-label={playing ? 'Pausa' : 'Reproducir'}>
          {playing ? <Icon d="M7 5h4v14H7zM13 5h4v14h-4z" /> : <Icon d="M8 5v14l11-7z" />}
        </button>
        <button onClick={() => send('next')} aria-label="Siguiente"><Icon d="M16 6h2v12h-2zM6 18l8.5-6L6 6z" /></button>
      </div>
    </div>
  )
}

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d={d} /></svg>
)
