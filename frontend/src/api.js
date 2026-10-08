export const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
export const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws'
export const VIDEO_URL = API_URL + '/video'

export async function getEvents() {
  const r = await fetch(API_URL + '/api/events')
  if (!r.ok) throw new Error('events ' + r.status)
  return r.json()
}
export async function getConfig() {
  const r = await fetch(API_URL + '/api/config')
  if (!r.ok) throw new Error('config ' + r.status)
  return r.json()
}
export async function testAlert() {
  const r = await fetch(API_URL + '/api/test-alert', { method: 'POST' })
  if (!r.ok) throw new Error('test alert failed (' + r.status + ')')
  return r.json()
}
export async function putConfig(cfg) {
  const r = await fetch(API_URL + '/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  if (!r.ok) throw new Error('save failed (' + r.status + ')')
  return r.json().catch(() => ({}))
}
