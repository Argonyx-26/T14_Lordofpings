// Motion for the Argus site. No dependencies, works offline, and does nothing under prefers-reduced-motion.
//   1. the eye: scrolling through #see opens an aperture onto real footage (sets --r and --p)
//   2. (scrolling is left native)
//   3. sections come into focus as they arrive; eyebrows decode; big numbers count up
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches

  // 1. the eye ----------------------------------------------------------------------------------------------
  const ap = document.getElementById('see')
  const updateEye = () => {
    if (!ap) return
    const rect = ap.getBoundingClientRect()
    const span = ap.offsetHeight - innerHeight
    const p = Math.min(1, Math.max(0, -rect.top / Math.max(1, span)))
    const e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2          // ease in-out cubic
    const max = Math.hypot(innerWidth, innerHeight) / 2 + 40
    const min = Math.min(innerWidth, innerHeight) * 0.17
    ap.style.setProperty('--r', `${(min + (max - min) * e).toFixed(1)}px`)
    ap.style.setProperty('--p', e.toFixed(3))
  }
  if (!reduce) { updateEye(); addEventListener('scroll', () => requestAnimationFrame(updateEye), { passive: true }); addEventListener('resize', updateEye) }

  // 2. scrolling stays native: an inertial wheel handler called scrollTo every frame, and with the page's
  //    scroll-behavior: smooth each call restarted a smooth scroll, which stuttered on laptop touchpads

  // 3. reveals ------------------------------------------------------------------------------------------------
  const GLYPHS = '▮▯◆◇▲△●○01ABCDEFHKLMNPRSTUVXYZ'
  const decode = (el) => {
    const text = el.textContent, t0 = performance.now(), ms = 520
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / ms), fixed = Math.floor(p * text.length)
      el.textContent = text.slice(0, fixed) + [...text.slice(fixed)].map((c) => (c === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join('')
      if (p < 1) requestAnimationFrame(tick); else el.textContent = text
    }
    requestAnimationFrame(tick)
  }
  const count = (el) => {
    const raw = el.textContent.trim(), m = raw.match(/^([\d,.]+)(.*)$/)
    if (!m) return
    const n = parseFloat(m[1].replace(/,/g, '')), dec = (m[1].split('.')[1] || '').length, t0 = performance.now(), ms = 1400
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / ms), v = n * (1 - Math.pow(1 - p, 4))
      el.textContent = v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[2]
      if (p < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }
  if (reduce || !('IntersectionObserver' in window)) return
  const targets = document.querySelectorAll('section h2.display, section .lead:not([data-scrub]), .funnel > div, .results > div, section table, section figure, .steps > *, .features > *, .team > *, .member')
  targets.forEach((el) => el.setAttribute('data-reveal', ''))
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue
      const el = en.target
      el.classList.add('in')
      el.querySelectorAll('.n').forEach(count)
      io.unobserve(el)
    }
  }, { rootMargin: '0px 0px -12% 0px', threshold: 0.12 })
  targets.forEach((el) => io.observe(el))
  const eo = new IntersectionObserver((entries) => {
    for (const en of entries) if (en.isIntersecting) { decode(en.target); eo.unobserve(en.target) }
  }, { threshold: 1 })
  document.querySelectorAll('section .eyebrow').forEach((el) => eo.observe(el))
})()
