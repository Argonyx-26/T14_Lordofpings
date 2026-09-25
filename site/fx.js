// Effects for the Argus site, layered on top of motion.js. No dependencies, works offline, every effect checks that
// its element exists (the judges' page shares this file) and does nothing, or draws one still frame, under
// prefers-reduced-motion.
//   1. attention field: a dithered WebGL field behind the hero that drifts and follows the cursor like the eye's gaze
//   2. convergence: signals travel from each source card; alone they fade out, together they open an incident
//   3. scroll-lit words: key sentences light up word by word as they scroll past
//   4. signal ticker: real events from the replay snapshot, looping under the hero
//   5. small things: scramble on hover, reticle cursor, scroll progress, glowing card borders, footer clock and wordmark
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const fine = matchMedia('(pointer: fine)').matches
  const GLYPHS = '▮▯◆◇▲△●○01ABCDEFHKLMNPRSTUVXYZ'

  // 1. attention field ----------------------------------------------------------------------------------------
  const hero = document.querySelector('.hero')
  if (hero) {
    const cv = document.createElement('canvas')
    cv.className = 'field'
    cv.setAttribute('aria-hidden', 'true')
    const gl = cv.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' })
    if (gl) {
      hero.prepend(cv)
      const VS = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'
      const FS = `precision mediump float;
uniform vec2 R;uniform float T;uniform vec2 M;
float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float n(vec2 p){vec2 i=floor(p),f=fract(p),u=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),u.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),u.x),u.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}
float b2(vec2 a){a=floor(a);return fract(dot(a,vec2(.5,a.y*.75)));}
float b4(vec2 a){return b2(.5*a)*.25+b2(a);}
float b8(vec2 a){return b4(.5*a)*.25+b2(a);}
void main(){
  vec2 uv=gl_FragCoord.xy/R;vec2 S=R/min(R.x,R.y)*2.4;vec2 p=uv*S;float t=T*.045;
  vec2 q=vec2(fbm(p+t),fbm(p+vec2(5.2,1.3)-t));
  float f=fbm(p+2.4*q+vec2(t*.7,-t*.4));
  vec2 m=M*S;float d=length(p-m);
  float gaze=exp(-d*d*1.6);
  float ring=exp(-pow((d-.55-.03*sin(T*.9))*9.,2.));
  float v=smoothstep(.32,.95,f)*.62+gaze*.26+ring*(.42+.2*f);
  v*=mix(.2,1.,smoothstep(.1,.3,d));
  v*=(.18+.82*smoothstep(.05,.95,uv.x))*(.35+.65*smoothstep(0.,.85,uv.y));
  float lv=clamp(floor(v*4.+b8(gl_FragCoord.xy)-.25),0.,3.);
  vec3 c=vec3(.047,.051,.059);
  if(lv>.5)c=vec3(.105,.11,.125);
  if(lv>1.5)c=vec3(.30,.15,.07);
  if(lv>2.5)c=mix(vec3(.30,.15,.07),vec3(.97,.42,.08),.8);
  gl_FragColor=vec4(c,1.);
}`
      const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s }
      const pr = gl.createProgram()
      gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr)
      if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { cv.remove() } else {
        gl.useProgram(pr)
        gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
        const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
        const uR = gl.getUniformLocation(pr, 'R'), uT = gl.getUniformLocation(pr, 'T'), uM = gl.getUniformLocation(pr, 'M')
        const CELL = 3                                                   // one dither cell = 3 CSS px, drawn pixelated
        const rest = innerWidth < 700 ? [0.8, 0.88] : [0.76, 0.72]   // phones: up in the corner, clear of the headline
        const mouse = [...rest], aim = [...rest]
        const size = () => { cv.width = Math.ceil(hero.clientWidth / CELL); cv.height = Math.ceil(hero.clientHeight / CELL); gl.viewport(0, 0, cv.width, cv.height) }
        let prev = 0
        const draw = (now) => {
          const k = prev ? 1 - Math.exp(-Math.min(100, now - prev) / 320) : 0   // the gaze eases over ~1 s at any frame rate
          prev = now
          mouse[0] += (aim[0] - mouse[0]) * k; mouse[1] += (aim[1] - mouse[1]) * k
          gl.uniform2f(uR, cv.width, cv.height); gl.uniform1f(uT, now / 1000); gl.uniform2f(uM, mouse[0], mouse[1])
          gl.drawArrays(gl.TRIANGLES, 0, 3)
        }
        size(); draw(9000)
        new ResizeObserver(() => { size(); draw(performance.now() + 9000) }).observe(hero)
        if (!reduce) {
          hero.addEventListener('pointermove', (e) => { const r = hero.getBoundingClientRect(); aim[0] = (e.clientX - r.left) / r.width; aim[1] = 1 - (e.clientY - r.top) / r.height })
          hero.addEventListener('pointerleave', () => { aim[0] = rest[0]; aim[1] = rest[1] })
          let visible = true, raf = 0
          const loop = (now) => { draw(now + 9000); raf = visible && !document.hidden ? requestAnimationFrame(loop) : 0 }
          const wake = () => { if (!raf && visible && !document.hidden) raf = requestAnimationFrame(loop) }
          new IntersectionObserver(([en]) => { visible = en.isIntersecting; wake() }).observe(hero)
          document.addEventListener('visibilitychange', wake)
        }
      }
    }
  }

  // 2. convergence --------------------------------------------------------------------------------------------
  const sig = document.querySelector('.signals')
  const cards = sig ? [...sig.querySelectorAll('.signal')] : []
  const node = sig && sig.querySelector('.together')
  if (sig && cards.length === 3 && node) {
    const COLORS = ['#5b8def', '#26a88a', '#d9669f']                    // camera, phones, doors: the console's source colours
    cards.forEach((c, i) => c.style.setProperty('--c', COLORS[i]))
    const cv = document.createElement('canvas')
    cv.className = 'wires'; cv.setAttribute('aria-hidden', 'true')
    sig.prepend(cv)
    sig.classList.add('wired')
    const ctx = cv.getContext('2d')
    let paths = [], dpr = 1, on = false

    // a wire: down from the card, along a bus under the row, then up into the incident card
    const build = () => {
      on = getComputedStyle(cv).display !== 'none'
      if (!on) return
      dpr = Math.min(2, devicePixelRatio || 1)
      const box = sig.getBoundingClientRect()
      cv.width = box.width * dpr; cv.height = box.height * dpr
      const nb = node.getBoundingClientRect()
      const ex = nb.left - box.left, ey = nb.bottom - box.top - 26
      paths = cards.map((c, i) => {
        const b = c.getBoundingClientRect()
        const x0 = b.left - box.left + b.width / 2, y0 = b.bottom - box.top
        const bus = y0 + 16 + i * 8, r = 10, xe = ex - 30
        const pts = [[x0, y0], [x0, bus - r]]
        for (let s = 1; s <= 8; s++) { const a = (s / 8) * Math.PI / 2; pts.push([x0 + r - r * Math.cos(a), bus - r + r * Math.sin(a)]) }
        pts.push([xe, bus])
        for (let s = 1; s <= 16; s++) {                                   // cubic up into the card's left edge
          const t = s / 16, u = 1 - t
          pts.push([u * u * u * xe + 3 * u * u * t * (xe + 22) + 3 * u * t * t * (ex - 16) + t * t * t * ex,
                    u * u * u * bus + 3 * u * u * t * bus + 3 * u * t * t * ey + t * t * t * ey])
        }
        const len = [0]
        for (let k = 1; k < pts.length; k++) len.push(len[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]))
        return { pts, len, total: len[len.length - 1] }
      })
    }
    const at = (p, d) => {
      d = Math.max(0, Math.min(p.total, d))
      let k = 1; while (k < p.len.length - 1 && p.len[k] < d) k++
      const f = (d - p.len[k - 1]) / Math.max(1e-6, p.len[k] - p.len[k - 1]), a = p.pts[k - 1], b = p.pts[k]
      return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]
    }
    const stroke = (p, d0, d1) => {
      ctx.beginPath()
      const steps = Math.max(2, Math.ceil((d1 - d0) / 4))
      for (let s = 0; s <= steps; s++) { const q = at(p, d0 + (d1 - d0) * (s / steps)); s ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]) }
      ctx.stroke()
    }

    const pulses = []
    let flash = 0, nextLone = 600, nextFuse = 2200, last = 0
    const ping = (i) => { cards[i].style.setProperty('--ping', '1'); setTimeout(() => cards[i].style.setProperty('--ping', '0'), 260) }
    const emit = (i, fused, now) => { pulses.push({ i, t0: now, dur: fused ? 1700 : 1500 + Math.random() * 500, die: fused ? 1.01 : 0.35 + Math.random() * 0.3, fused }); ping(i) }

    const frame = (now) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, cv.width, cv.height)
      ctx.lineCap = 'round'; ctx.lineJoin = 'round'
      ctx.strokeStyle = 'rgba(20,21,24,.22)'; ctx.lineWidth = 1.25
      paths.forEach((p) => stroke(p, 0, p.total))
      if (!reduce) {
        if (now > nextLone) { emit((Math.random() * 3) | 0, false, now); nextLone = now + 450 + Math.random() * 900 }
        if (now > nextFuse) { [0, 1, 2].forEach((i) => emit(i, true, now)); nextFuse = now + 4200 + Math.random() * 1400 }
        let arrived = 0
        for (let k = pulses.length - 1; k >= 0; k--) {
          const u = pulses[k], p = paths[u.i], prog = (now - u.t0) / u.dur
          const e = u.fused ? 1 - Math.pow(1 - Math.min(1, prog), 2.2) : prog
          if (prog >= 1 || e > u.die + 0.12) { if (u.fused && prog >= 1) arrived++; pulses.splice(k, 1); continue }
          const fade = u.fused ? 1 : Math.max(0, Math.min(1, (u.die + 0.12 - e) / 0.12))
          const d = e * p.total
          ctx.globalAlpha = fade
          ctx.strokeStyle = COLORS[u.i]; ctx.lineWidth = 2.5
          stroke(p, d - 46, d)
          const hd = at(p, d); ctx.fillStyle = COLORS[u.i]; ctx.beginPath(); ctx.arc(hd[0], hd[1], 3.2, 0, 7); ctx.fill()
          ctx.globalAlpha = 1
        }
        if (arrived) flash = 1
        flash *= Math.pow(0.35, Math.min(64, now - last) / 1000)
        node.style.setProperty('--flash', flash.toFixed(3))
      }
      last = now
    }
    let raf = 0, visible = false
    const loop = (now) => { if (on) frame(now); raf = on && visible && !document.hidden && !reduce ? requestAnimationFrame(loop) : 0 }
    const wake = () => { if (!raf && on && visible && !document.hidden && !reduce) { last = performance.now(); nextLone = last + 300; nextFuse = last + 1200; raf = requestAnimationFrame(loop) } }
    new ResizeObserver(() => { build(); if (on) frame(performance.now()); wake() }).observe(sig)
    new IntersectionObserver(([en]) => { visible = en.isIntersecting; wake() }).observe(sig)
    document.addEventListener('visibilitychange', wake)
  }

  // 3. scroll-lit words ---------------------------------------------------------------------------------------
  const lit = reduce ? [] : [...document.querySelectorAll('[data-scrub]')]
  lit.forEach((el) => {
    const words = el.textContent.trim().split(/\s+/)
    el.setAttribute('aria-label', el.textContent.trim())
    el.textContent = ''
    words.forEach((w, i) => { const s = document.createElement('span'); s.className = 'w'; s.setAttribute('aria-hidden', 'true'); s.textContent = w; el.append(s, i < words.length - 1 ? ' ' : '') })
    el.classList.add('scrub')
  })
  const scrub = () => {
    for (const el of lit) {
      const r = el.getBoundingClientRect()
      const p = Math.max(0, Math.min(1, (innerHeight * 0.88 - r.top) / (r.height + innerHeight * 0.38)))
      const ws = el.children, on = Math.round(p * ws.length)
      for (let i = 0; i < ws.length; i++) ws[i].classList.toggle('on', i < on)
    }
  }
  if (lit.length) { scrub(); addEventListener('scroll', () => requestAnimationFrame(scrub), { passive: true }); addEventListener('resize', scrub) }

  // 4. signal ticker: loop it seamlessly by repeating the track once ------------------------------------------
  const track = document.querySelector('.ticker-track')
  if (track && !reduce) { track.innerHTML += track.innerHTML; track.querySelectorAll('li').forEach((li, i, all) => { if (i >= all.length / 2) li.setAttribute('aria-hidden', 'true') }); track.classList.add('run') }

  // 5a. scramble on hover (width locked so the layout never moves) ---------------------------------------------
  if (!reduce && fine) document.querySelectorAll('nav .links a, .btn').forEach((el) => {
    if (el.children.length) return
    const text = el.textContent
    let raf = 0
    el.addEventListener('pointerenter', () => {
      cancelAnimationFrame(raf)
      el.style.minWidth = `${el.getBoundingClientRect().width}px`
      const t0 = performance.now()
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / 380), fixed = Math.floor(p * text.length)
        el.textContent = text.slice(0, fixed) + [...text.slice(fixed)].map((c) => (c === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join('')
        if (p < 1) raf = requestAnimationFrame(tick); else { el.textContent = text; el.style.minWidth = '' }
      }
      raf = requestAnimationFrame(tick)
    })
  })

  // 5b. reticle: the eye keeps track of the pointer --------------------------------------------------------------
  if (!reduce && fine) {
    const ret = document.createElement('div')
    ret.className = 'reticle'; ret.setAttribute('aria-hidden', 'true')
    document.body.append(ret)
    let x = -100, y = -100, tx = -100, ty = -100, hot = false, raf = 0
    const move = () => {
      x += (tx - x) * 0.22; y += (ty - y) * 0.22
      ret.style.transform = `translate(${x}px, ${y}px) scale(${hot ? 1.55 : 1})`
      raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.3 ? requestAnimationFrame(move) : 0
    }
    addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse') return
      tx = e.clientX; ty = e.clientY
      hot = !!(e.target.closest && e.target.closest('a, button, summary'))
      ret.classList.toggle('hot', hot); ret.classList.add('on')
      if (!raf) raf = requestAnimationFrame(move)
    }, { passive: true })
    document.addEventListener('mouseout', (e) => { if (!e.relatedTarget) ret.classList.remove('on') })
  }

  // 5c. scroll progress under the nav -------------------------------------------------------------------------------
  const nav = document.querySelector('nav')
  if (nav) {
    const bar = document.createElement('div')
    bar.className = 'progress'; bar.setAttribute('aria-hidden', 'true')
    nav.append(bar)
    const upd = () => bar.style.transform = `scaleX(${(scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight)).toFixed(4)})`
    upd(); addEventListener('scroll', upd, { passive: true }); addEventListener('resize', upd)
  }

  // 5d. borders that light up around the pointer (the grid's 1 px gaps are the borders) ------------------------
  if (fine) document.querySelectorAll('.features, .funnel').forEach((g) => {
    g.addEventListener('pointermove', (e) => { const r = g.getBoundingClientRect(); g.style.setProperty('--gx', `${e.clientX - r.left}px`); g.style.setProperty('--gy', `${e.clientY - r.top}px`); g.classList.add('lit') })
    g.addEventListener('pointerleave', () => g.classList.remove('lit'))
  })

  // 5e. footer: a clock that says the eye is still watching, and a wordmark the light follows -----------------------
  const clock = document.querySelector('[data-clock]')
  if (clock) {
    const fmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    const tickClock = () => { clock.textContent = `${fmt.format(new Date())} IST` }
    tickClock(); setInterval(tickClock, 1000)
  }
  const mark = document.querySelector('.bigmark')
  if (mark) {
    if (fine && !reduce) mark.parentElement.addEventListener('pointermove', (e) => { const r = mark.getBoundingClientRect(); mark.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`); mark.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`) })
    if (reduce || !('IntersectionObserver' in window)) mark.classList.add('in')
    else { const io = new IntersectionObserver(([en]) => { if (en.isIntersecting) { mark.classList.add('in'); io.disconnect() } }, { threshold: 0.25 }); io.observe(mark) }
  }
})()
