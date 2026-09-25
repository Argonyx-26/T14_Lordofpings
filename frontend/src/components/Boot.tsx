import { AnimatePresence, m } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import type { ArgusEvent, Clock } from '../types'
import { ArgusEye, type EyeCamera } from './ArgusEye'
import { Decode } from './Motion'

const STEPS = ['Opening the eye', 'Linking six cameras', 'Door sensors', 'Phone locations', 'Fusion engine', 'Watching']

/** The eye opens while the console links up, then flies into its place in the top band. */
export function Boot({ ready, linked, clock, events, cameras, onLeave, onDone }: {
  ready: boolean; linked: boolean; clock: Clock | null; events: ArgusEvent[]; cameras: EyeCamera[]
  onLeave: () => void   // the eye hands over to the band (shared-element flight)
  onDone: () => void    // the overlay has faded out
}) {
  const [open, setOpen] = useState(0)
  const [pct, setPct] = useState(0)
  const [leaving, setLeaving] = useState(false)
  const started = useRef(0)
  const shown = useRef(0)

  // the lid opens over 900 ms
  useEffect(() => {
    let raf = 0
    const t0 = performance.now() + 150
    const step = (now: number) => {
      const p = Math.max(0, Math.min(1, (now - t0) / 900))
      setOpen(p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2)
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [])

  // honest progress: 10 % on start, config + first live snapshot carry most of it, and at least 1.8 s on screen
  useEffect(() => {
    let raf = 0
    if (!started.current) started.current = performance.now()
    const tick = () => {
      const t = performance.now() - started.current
      const target = Math.min(100, 10 + (ready ? 35 : 0) + (linked ? 35 : 0) + Math.min(20, (t / 1800) * 20))
      shown.current += (target - shown.current) * 0.12
      setPct(Math.round(shown.current))
      if (shown.current > 99.4 && t > 1800) { setLeaving(true); return }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [ready, linked])

  // the parent re-renders on every live tick with new callbacks: keep the latest in refs so timers aren't reset
  const cb = useRef({ onLeave, onDone })
  useEffect(() => { cb.current = { onLeave, onDone } })
  useEffect(() => {
    if (!leaving) return
    cb.current.onLeave()
    const id = setTimeout(() => cb.current.onDone(), 1200)   // the fade normally finishes first; this covers a frozen tab
    return () => clearTimeout(id)
  }, [leaving])
  // never hold the console hostage: whatever the network or a throttled background tab does, hand over by 4.5 s
  useEffect(() => { const id = setTimeout(() => setLeaving(true), 4500); return () => clearTimeout(id) }, [])

  const step = STEPS[Math.min(STEPS.length - 1, Math.floor((pct / 100) * STEPS.length))]
  return (
    <AnimatePresence onExitComplete={() => cb.current.onDone()}>
      {!leaving && (
        <m.div key="boot" className="boot fixed inset-0 z-[70] flex flex-col items-center justify-center"
          initial={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.45, ease: [0.4, 0, 1, 1] } }}>
          <span className="num absolute right-6 top-5 text-[13px] tracking-[0.2em] text-[var(--color-fg-3)]">
            {String(pct).padStart(3, '0')}<span className="text-[var(--color-fg-4)]">%</span>
          </span>
          <span className="eyebrow absolute left-6 top-5">ARGONYX '26 · PS5</span>
          <m.div layoutId="argus-eye" className="relative" style={{ width: 'min(340px, 62vw)', height: 'min(340px, 62vw)' }}>
            <ArgusEye size={340} level="clear" score={null} events={events} clock={clock} cameras={cameras} open={open} detail="full" />
          </m.div>
          <m.div className="mt-8 text-center" initial={{ opacity: 0, y: 8, filter: 'blur(6px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            transition={{ delay: 0.5, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
            <div className="wordmark text-[64px] leading-none text-[var(--color-fg)]">Argus</div>
            <div className="mt-2 font-[var(--font-serif)] text-[20px] italic text-[var(--color-fg-2)]" style={{ fontFamily: 'var(--font-serif)' }}>
              We don't watch more. We notice sooner.
            </div>
            <div className="num mt-6 h-4 text-[11.5px] uppercase tracking-[0.22em] text-[var(--color-accent)]"><Decode text={step} ms={320} /></div>
          </m.div>
          <button onClick={() => setLeaving(true)} className="absolute bottom-6 text-[11px] text-[var(--color-fg-4)] transition hover:text-[var(--color-fg-2)]">
            skip
          </button>
        </m.div>
      )}
    </AnimatePresence>
  )
}
