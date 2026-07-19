import { useCallback, useRef, useState } from 'react'
import { registerPlugin } from '@capacitor/core'
import type {
  BackgroundGeolocationPlugin,
  Location,
  CallbackError,
} from '@capacitor-community/background-geolocation'
import { appendPing, getPings, type PingLogEntry } from '../lib/pingLog'

// The package ships only native (iOS/Android) sources + type definitions —
// no JS/web entry point (no "main"/"exports" in its package.json) — so the
// runtime plugin object is obtained via Capacitor's registerPlugin, per the
// package's own README, not via a named export from the package itself.
const BackgroundGeolocation = registerPlugin<BackgroundGeolocationPlugin>('BackgroundGeolocation')

interface UseBackgroundLocationResult {
  isTracking: boolean
  error: string | null
  pingCount: number
  start: () => Promise<void>
  stop: () => Promise<void>
}

export function useBackgroundLocation(): UseBackgroundLocationResult {
  const [isTracking, setIsTracking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pingCount, setPingCount] = useState<number>(() => getPings().length)
  const watcherIdRef = useRef<string | null>(null)

  const start = useCallback(async () => {
    setError(null)
    const id = await BackgroundGeolocation.addWatcher(
      {
        backgroundTitle: 'Atlas Field Force',
        backgroundMessage: 'Tracking your location for the field-force spike',
        requestPermissions: true,
        stale: false,
        distanceFilter: 0,
      },
      (location?: Location, watcherError?: CallbackError) => {
        if (watcherError) {
          setError(watcherError.code ?? watcherError.message)
          return
        }
        if (location) {
          const entry: PingLogEntry = {
            latitude: location.latitude,
            longitude: location.longitude,
            accuracy: location.accuracy,
            // `time` is nullable in stale fixes; fall back to wall clock.
            time: location.time ?? Date.now(),
          }
          appendPing(entry)
          setPingCount(getPings().length)
        }
      },
    )
    watcherIdRef.current = id
    setIsTracking(true)
  }, [])

  const stop = useCallback(async () => {
    if (watcherIdRef.current) {
      await BackgroundGeolocation.removeWatcher({ id: watcherIdRef.current })
      watcherIdRef.current = null
    }
    setIsTracking(false)
  }, [])

  return { isTracking, error, pingCount, start, stop }
}
