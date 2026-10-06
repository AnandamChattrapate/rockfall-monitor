import { useEffect, useState } from 'react'
import { VIDEO_URL, getConfig, putConfig } from '../api.js'

export const THETA_MOD = 0.4
export const THETA_HIGH = 0.7
const COLORS = { LOW: 'var(--low)', MODERATE: 'var(--mod)', HIGH: 'var(--high)' }
const levelOf = (r) => (r >= THETA_HIGH ? 'HIGH' : r >= THETA_MOD ? 'MODERATE' : 'LOW')

export function Panel({ title, children, className = '' }) {
  return (
    <section className={'panel ' + className}>
      <h2>{title}</h2>
      {children}
    </section>
  )
}

export function Camera() {
  const [failed, setFailed] = useState(false)
  const [nonce, setNonce] = useState(0)
  return (
    <Panel title="Live camera" className="camera">
      {failed ? (
        <div className="offline">
          <p>Camera offline. Cannot load video stream.</p>
          <button onClick={() => { setFailed(false); setNonce((n) => n + 1) }}>Retry</button>
        </div>
      ) : (
        <img src={`${VIDEO_URL}?n=${nonce}`} alt="Live camera feed" onError={() => setFailed(true)} />
      )}
    </Panel>
  )
}

export function Gauge({ risk = 0, level }) {
  const lv = level || levelOf(risk)
  const r = Math.max(0, Math.min(1, risk))
  const R = 80, C = Math.PI * R
  const color = COLORS[lv] || COLORS.LOW
  return (
    <Panel title="Risk gauge">
      <svg viewBox="0 0 200 120" className="gauge" role="img" aria-label={`Risk ${r.toFixed(2)} ${lv}`}>
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="var(--track)" strokeWidth="14" strokeLinecap="round" />
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke={color} strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${C * r} ${C}`} style={{ transition: 'stroke-dasharray .3s' }} />
        <text x="100" y="90" textAnchor="middle" className="gauge-num" fill={color}>{r.toFixed(2)}</text>
        <text x="100" y="112" textAnchor="middle" className="gauge-lbl" fill={color}>{lv}</text>
      </svg>
    </Panel>
  )
}

export function Trend({ history }) {
  const W = 600, H = 200, pl = 34, pr = 8, pt = 8, pb = 22
  const now = history.length ? history[history.length - 1].ts : Date.now() / 1000
  const x = (ts) => pl + ((ts - (now - 600)) / 600) * (W - pl - pr)
  const y = (v) => pt + (1 - Math.max(0, Math.min(1, v))) * (H - pt - pb)
  const pts = history.map((p) => `${x(p.ts).toFixed(1)},${y(p.risk).toFixed(1)}`).join(' ')
  return (
    <Panel title="Risk trend (10 min)">
      <svg viewBox={`0 0 ${W} ${H}`} className="trend" role="img" aria-label="Risk trend">
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={pl} x2={W - pr} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
            <text x={pl - 4} y={y(v) + 3} textAnchor="end" className="axis">{v.toFixed(2)}</text>
          </g>
        ))}
        <line x1={pl} x2={W - pr} y1={y(THETA_MOD)} y2={y(THETA_MOD)} stroke="var(--mod)" strokeDasharray="5 4" />
        <line x1={pl} x2={W - pr} y1={y(THETA_HIGH)} y2={y(THETA_HIGH)} stroke="var(--high)" strokeDasharray="5 4" />
        <text x={W - pr} y={y(THETA_MOD) - 3} textAnchor="end" className="axis" fill="var(--mod)">θ_mod 0.40</text>
        <text x={W - pr} y={y(THETA_HIGH) - 3} textAnchor="end" className="axis" fill="var(--high)">θ_high 0.70</text>
        <text x={pl} y={H - 6} className="axis">-10 min</text>
        <text x={W - pr} y={H - 6} textAnchor="end" className="axis">now</text>
        {pts && <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />}
      </svg>
    </Panel>
  )
}

export function Tracks({ tracks = [] }) {
  return (
    <Panel title={`Active tracks (${tracks.length})`}>
      <div className="scroll">
        <table>
          <thead><tr><th>ID</th><th>Conf</th><th>Persist</th><th>Growth</th><th>Risk</th></tr></thead>
          <tbody>
            {tracks.length === 0 && <tr><td colSpan="5" className="muted">No active tracks</td></tr>}
            {tracks.map((t) => (
              <tr key={t.id}>
                <td>#{t.id}</td><td>{t.conf.toFixed(2)}</td><td>{t.persistence.toFixed(2)}</td>
                <td>{t.growth.toFixed(2)}</td>
                <td style={{ color: COLORS[levelOf(t.risk)] }}>{t.risk.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

export function EventLog({ events }) {
  return (
    <Panel title="Event log">
      <div className="scroll log">
        {events.length === 0 && <p className="muted">No events</p>}
        {events.map((e) => (
          <div key={e.id ?? `${e.ts}-${e.type}`} className={'ev ev-' + e.type}>
            <span className="time">{new Date(e.ts * 1000).toLocaleTimeString()}</span>
            <span className="badge">{e.type}</span>
            <span className="lvl" style={{ color: COLORS[e.level] }}>{e.level}</span>
            <span>R {Number(e.risk).toFixed(2)}</span>
            <span className="msg">{e.region ? `[${e.region}] ` : ''}{e.message}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

export function Telemetry({ tick, status }) {
  return (
    <header className="telemetry">
      <h1>Rockfall Monitor</h1>
      <span>FPS <b>{tick ? tick.fps.toFixed(1) : '--'}</b></span>
      <span>Motion <b>{tick ? (tick.motion_ratio * 100).toFixed(1) + '%' : '--'}</b></span>
      <span>Detector <b>{tick ? tick.detector_mode : '--'}</b></span>
      <span className={'conn conn-' + status}><i />{status}</span>
    </header>
  )
}

const FIELDS = [
  ['theta_mod', 'θ_mod', 0.01], ['theta_high', 'θ_high', 0.01],
  ['k', 'k (debounce)', 1], ['cooldown', 'Cooldown (s)', 1],
]

export function Settings() {
  const [form, setForm] = useState({})
  const [msg, setMsg] = useState('')
  const [raw, setRaw] = useState({})

  useEffect(() => {
    getConfig().then((c) => {
      setRaw(c)
      const f = {}
      for (const [key] of FIELDS) { const kk = pick(c, key); if (kk) f[key] = c[kk] }
      setForm(f)
    }).catch(() => setMsg('Cannot load config'))
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    const body = { ...raw }
    for (const [key] of FIELDS) {
      if (form[key] === undefined || form[key] === '') continue
      body[pick(raw, key) || key] = Number(form[key])
    }
    try { await putConfig(body); setMsg('Saved') } catch (err) { setMsg(err.message) }
  }

  return (
    <Panel title="Settings">
      <form onSubmit={submit} className="settings">
        {FIELDS.map(([key, label, step]) => (
          <label key={key}>{label}
            <input type="number" step={step} value={form[key] ?? ''}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
          </label>
        ))}
        <button type="submit">Save</button>
        <span className="muted">{msg}</span>
      </form>
    </Panel>
  )
}

// Map a logical field to the key the backend uses (tolerates theta_mod / mod_threshold / cooldown_s variants).
function pick(c, key) {
  const alts = {
    theta_mod: ['theta_mod', 'mod_threshold'],
    theta_high: ['theta_high', 'high_threshold'],
    k: ['k', 'debounce_k', 'debounce'],
    cooldown: ['cooldown', 'cooldown_s', 'cooldown_sec', 'cooldown_seconds'],
  }[key]
  return alts.find((a) => a in c) || null
}
