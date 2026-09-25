import { useEffect, useRef } from 'react'

const VS = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'
// Drifting noise, ordered-dithered to four tones, brightest in a halo around the eye at the centre.
const FS = `precision mediump float;
uniform vec2 R;uniform float T;
float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float n(vec2 p){vec2 i=floor(p),f=fract(p),u=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),u.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),u.x),u.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}
float b2(vec2 a){a=floor(a);return fract(dot(a,vec2(.5,a.y*.75)));}
float b4(vec2 a){return b2(.5*a)*.25+b2(a);}
float b8(vec2 a){return b4(.5*a)*.25+b2(a);}
void main(){
  vec2 S=R/min(R.x,R.y);vec2 p=(gl_FragCoord.xy/R-.5)*S;float t=T*.05;
  vec2 q=vec2(fbm(p*2.2+t),fbm(p*2.2+vec2(5.2,1.3)-t));
  float f=fbm(p*2.2+2.4*q);
  float d=length(p-vec2(0.,.08));
  float halo=exp(-pow((d-.42)*4.,2.));
  float v=(smoothstep(.35,.95,f)*.55+halo*.5)*(1.-smoothstep(.25,1.1,d));
  float lv=clamp(floor(v*4.+b8(gl_FragCoord.xy)-.25),0.,3.);
  vec3 c=vec3(.031,.039,.051);
  if(lv>.5)c=vec3(.07,.09,.12);
  if(lv>1.5)c=vec3(.09,.14,.22);
  if(lv>2.5)c=vec3(.16,.26,.4);
  gl_FragColor=vec4(c,1.);
}`

/** Dithered field behind the boot sequence. Draws one still frame under reduced motion, nothing without WebGL. */
export function DitherField({ cell = 3 }: { cell?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current
    const gl = cv?.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' })
    if (!cv || !gl) return
    const sh = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); return s }
    const pr = gl.createProgram()
    gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr)
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { cv.style.display = 'none'; return }
    gl.useProgram(pr)
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
    const uR = gl.getUniformLocation(pr, 'R'), uT = gl.getUniformLocation(pr, 'T')
    const size = () => { cv.width = Math.ceil(cv.clientWidth / cell); cv.height = Math.ceil(cv.clientHeight / cell); gl.viewport(0, 0, cv.width, cv.height) }
    const draw = (now: number) => { gl.uniform2f(uR, cv.width, cv.height); gl.uniform1f(uT, now / 1000 + 20); gl.drawArrays(gl.TRIANGLES, 0, 3) }
    size(); draw(0)
    const ro = new ResizeObserver(() => { size(); draw(performance.now()) }); ro.observe(cv)
    let raf = 0
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const loop = (now: number) => { draw(now); raf = requestAnimationFrame(loop) }
      raf = requestAnimationFrame(loop)
    }
    return () => { cancelAnimationFrame(raf); ro.disconnect() }   // the context goes with the canvas (losing it here would break StrictMode's remount)
  }, [cell])
  return <canvas ref={ref} aria-hidden="true" className="dither-field pointer-events-none absolute inset-0 h-full w-full" />
}
