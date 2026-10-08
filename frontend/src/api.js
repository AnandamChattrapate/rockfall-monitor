export const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
export const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws'
export const VIDEO_URL = API_URL + '/video'

// fetch() rejects with a bare "Failed to fetch" when the backend is down or CORS blocks it.
async function call(path, opts) {
  let r
  try {
    r = await fetch(API_URL + path, opts)
  } catch {
    throw new Error(`Cannot reach backend at ${API_URL}. Is it running?`)
  }
  if (!r.ok) throw new Error(`${path} failed (${r.status})`)
  return r.json()
}

export const getEvents = () => call('/api/events')
export const getConfig = () => call('/api/config')
export const testAlert = () => call('/api/test-alert', { method: 'POST' })
export const putConfig = (cfg) => call('/api/config', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(cfg),
})
