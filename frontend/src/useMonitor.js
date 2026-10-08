import { useEffect, useRef, useState } from 'react'
import { WS_URL, getEvents } from './api.js'
import { notify, playAlarm } from './alarm.js'

const WINDOW_S = 600
const MAX_EVENTS = 200

export function useMonitor() {
  const [tick, setTick] = useState(null)
  const [status, setStatus] = useState('connecting')
  const [history, setHistory] = useState([])
  const [events, setEvents] = useState([])
  const attempt = useRef(0)

  useEffect(() => {
    let alive = true
    getEvents()
      .then((list) => {
        if (!alive) return
        const arr = Array.isArray(list) ? list : list.events || []
        setEvents((cur) => merge(cur, arr))
      })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let ws, timer, closed = false
    const connect = () => {
      setStatus(attempt.current ? 'reconnecting' : 'connecting')
      ws = new WebSocket(WS_URL)
      ws.onopen = () => { attempt.current = 0; setStatus('connected') }
      ws.onmessage = (m) => {
        let d
        try { d = JSON.parse(m.data) } catch { return }
        setTick(d)
        const ts = d.ts || Date.now() / 1000
        setHistory((h) => {
          const next = [...h, { ts, risk: d.risk || 0 }]
          const cut = ts - WINDOW_S
          let i = 0
          while (i < next.length && next[i].ts < cut) i++
          return i ? next.slice(i) : next
        })
        const fresh = d.events || (d.event ? [d.event] : [])
        if (fresh.length) {
          setEvents((cur) => merge(cur, fresh))
          const alarm = fresh.find((e) => e.type === 'ALERT' || e.type === 'TEST')
          if (alarm) { playAlarm(); notify(alarm) }
        }
      }
      ws.onclose = () => {
        if (closed) return
        setStatus('disconnected')
        const delay = Math.min(10000, 500 * 2 ** attempt.current++)
        timer = setTimeout(connect, delay)
      }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => { closed = true; clearTimeout(timer); ws && ws.close() }
  }, [])

  return { tick, status, history, events }
}

function merge(cur, incoming) {
  const map = new Map()
  for (const e of [...incoming, ...cur]) map.set(e.id ?? `${e.ts}-${e.type}`, e)
  return [...map.values()].sort((a, b) => b.ts - a.ts).slice(0, MAX_EVENTS)
}
