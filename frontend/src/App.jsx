import { useMonitor } from './useMonitor.js'
import { Camera, Gauge, Trend, Tracks, EventLog, Telemetry, Settings } from './components/Panels.jsx'

export default function App() {
  const { tick, status, history, events } = useMonitor()
  return (
    <div className="app">
      <Telemetry tick={tick} status={status} />
      <main className="grid">
        <Camera />
        <Gauge risk={tick?.risk ?? 0} level={tick?.level} />
        <Trend history={history} />
        <Tracks tracks={tick?.tracks} />
        <EventLog events={events} />
        <Settings />
      </main>
    </div>
  )
}
