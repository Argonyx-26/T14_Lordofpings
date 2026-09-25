import { m, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

/**
 * Motion primitives. Each one says something changed, never decorates:
 *   Decode   a new title resolves out of scrambled glyphs, the way a signal becomes a finding
 *   BlurIn   a freshly written brief comes into focus
 *   Roll     a count rolls to its new value on a spring
 * All of them fall back to plain text under prefers-reduced-motion.
 */

const GLYPHS = '▮▯◆◇▲△●○01ABCDEFHKLMNPRSTUVXYZ'

export function Decode({ text, className, ms = 420 }: { text: string; className?: string; ms?: number }) {
  const reduce = useReducedMotion()
  const [shown, setShown] = useState(text)
  const first = useRef(true)
  useEffect(() => {
    if (reduce || first.current) { first.current = false; setShown(text); return }
    const start = performance.now()
    let raf = 0
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / ms)
      const fixed = Math.floor(p * text.length)
      setShown(text.slice(0, fixed) + [...text.slice(fixed)].map((c) => (c === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join(''))
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [text, ms, reduce])
  return <span className={className} aria-label={text}><span aria-hidden>{shown}</span></span>
}

export function BlurIn({ children, id, className }: { children: ReactNode; id: string; className?: string }) {
  const reduce = useReducedMotion()
  return (
    <m.div key={id} className={className}
      initial={reduce ? false : { opacity: 0, filter: 'blur(8px)', y: 4 }}
      animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </m.div>
  )
}

export function Roll({ value, format = (n) => Math.round(n).toLocaleString('en-US'), className }: {
  value: number; format?: (n: number) => string; className?: string
}) {
  const reduce = useReducedMotion()
  const el = useRef<HTMLSpanElement>(null)
  const from = useRef(value)
  // the animation owns the text node; React renders the span empty so the two never both write it
  useLayoutEffect(() => { if (el.current && !el.current.textContent) el.current.textContent = format(value) })
  useEffect(() => {
    const node = el.current
    if (!node) return
    if (reduce) { node.textContent = format(value); from.current = value; return }
    const stop = spring(from.current, value, (v) => { node.textContent = format(v) })
    from.current = value
    return stop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduce])
  return <span ref={el} className={className} aria-label={format(value)} />
}

/** A critically damped spring from a to b, calling back each frame; returns a stop function. */
function spring(a: number, b: number, onUpdate: (v: number) => void, stiffness = 90, damping = 20): () => void {
  let x = a, v = 0, raf = 0, last = performance.now()
  const step = (now: number) => {
    const dt = Math.min(0.032, (now - last) / 1000)
    last = now
    v += (stiffness * (b - x) - damping * v) * dt
    x += v * dt
    if (Math.abs(b - x) < 0.01 && Math.abs(v) < 0.01) { onUpdate(b); return }
    onUpdate(x)
    raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
  return () => cancelAnimationFrame(raf)
}
