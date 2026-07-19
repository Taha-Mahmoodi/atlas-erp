import { useState } from 'react'
import { useBackgroundLocation } from './hooks/useBackgroundLocation'
import { getPings, clearPings } from './lib/pingLog'

function App() {
  const { isTracking, error, pingCount, start, stop } = useBackgroundLocation()
  const [showLog, setShowLog] = useState(false)

  return (
    <div className="p-6 max-w-md mx-auto font-sans">
      <h1 className="text-xl font-bold mb-4">Field Force — Location Spike</h1>

      <div className="mb-4">
        <span className="font-semibold">Status: </span>
        {isTracking ? 'Tracking' : 'Stopped'}
      </div>

      {error && (
        <div className="mb-4 text-red-600">Error: {error}</div>
      )}

      <div className="mb-4">
        <span className="font-semibold">Pings logged: </span>
        {pingCount}
      </div>

      <div className="flex gap-2 mb-6">
        <button
          onClick={() => void start()}
          disabled={isTracking}
          className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-40"
        >
          Start
        </button>
        <button
          onClick={() => void stop()}
          disabled={!isTracking}
          className="px-4 py-2 bg-gray-600 text-white rounded disabled:opacity-40"
        >
          Stop
        </button>
        <button
          onClick={() => setShowLog((v) => !v)}
          className="px-4 py-2 bg-gray-200 rounded"
        >
          {showLog ? 'Hide log' : 'Show log'}
        </button>
        <button
          onClick={() => clearPings()}
          className="px-4 py-2 bg-gray-200 rounded"
        >
          Clear
        </button>
      </div>

      {showLog && (
        <ul className="text-xs font-mono space-y-1 max-h-96 overflow-y-auto">
          {getPings().slice(-50).reverse().map((p, i) => (
            <li key={i}>
              {new Date(p.time).toISOString()} — {p.latitude.toFixed(5)}, {p.longitude.toFixed(5)} (±{p.accuracy.toFixed(0)}m)
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default App
