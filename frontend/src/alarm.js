// Dashboard alarm: Web Audio siren + browser notification.
// Browsers block audio until the user interacts with the page, so sound must be armed by a click.
let ctx = null

export function armSound() {
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)()
  if (ctx.state === 'suspended') ctx.resume()
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission()
}

export function soundArmed() {
  return !!ctx && ctx.state === 'running'
}

export function playAlarm(seconds = 3) {
  if (!soundArmed()) return false
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  const t0 = ctx.currentTime
  osc.type = 'sawtooth'
  for (let t = 0; t < seconds; t += 0.5) {
    osc.frequency.setValueAtTime(1100, t0 + t)
    osc.frequency.setValueAtTime(700, t0 + t + 0.25)
  }
  gain.gain.setValueAtTime(0.15, t0)
  gain.gain.setValueAtTime(0, t0 + seconds)
  osc.connect(gain).connect(ctx.destination)
  osc.start(t0)
  osc.stop(t0 + seconds)
  return true
}

export function notify(ev) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  new Notification(ev.type === 'TEST' ? 'Rockfall test alert' : 'ROCKFALL ALERT', {
    body: ev.message, requireInteraction: ev.type === 'ALERT',
  })
}
