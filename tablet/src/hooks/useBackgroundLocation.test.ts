import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useBackgroundLocation } from './useBackgroundLocation'
import { clearPings, getPings } from '../lib/pingLog'

const addWatcherMock = vi.fn()
const removeWatcherMock = vi.fn()

// The plugin has no JS entry point of its own (native-only + types) — the
// real hook obtains it via @capacitor/core's registerPlugin (see
// useBackgroundLocation.ts), so that's the module under mock here, not
// '@capacitor-community/background-geolocation' itself.
vi.mock('@capacitor/core', () => ({
  registerPlugin: () => ({
    addWatcher: (...args: unknown[]) => addWatcherMock(...args),
    removeWatcher: (...args: unknown[]) => removeWatcherMock(...args),
  }),
}))

describe('useBackgroundLocation', () => {
  beforeEach(() => {
    clearPings()
    addWatcherMock.mockReset()
    removeWatcherMock.mockReset()
  })

  it('starts not tracking, with zero pings', () => {
    const { result } = renderHook(() => useBackgroundLocation())
    expect(result.current.isTracking).toBe(false)
    expect(result.current.pingCount).toBe(0)
  })

  it('start() calls addWatcher and flips isTracking to true', async () => {
    addWatcherMock.mockResolvedValue('watcher-1')
    const { result } = renderHook(() => useBackgroundLocation())

    await act(async () => {
      await result.current.start()
    })

    expect(addWatcherMock).toHaveBeenCalledOnce()
    expect(result.current.isTracking).toBe(true)
  })

  it('a location fix from the watcher callback is persisted and bumps pingCount', async () => {
    let capturedCallback: (location: unknown, error: unknown) => void = () => {}
    addWatcherMock.mockImplementation((_options: unknown, callback: typeof capturedCallback) => {
      capturedCallback = callback
      return Promise.resolve('watcher-1')
    })
    const { result } = renderHook(() => useBackgroundLocation())

    await act(async () => {
      await result.current.start()
    })
    act(() => {
      capturedCallback({ latitude: 10, longitude: 20, accuracy: 5, time: 12345 }, null)
    })

    expect(result.current.pingCount).toBe(1)
    expect(getPings()).toEqual([{ latitude: 10, longitude: 20, accuracy: 5, time: 12345 }])
  })

  it('a watcher error sets the error field without crashing', async () => {
    let capturedCallback: (location: unknown, error: unknown) => void = () => {}
    addWatcherMock.mockImplementation((_options: unknown, callback: typeof capturedCallback) => {
      capturedCallback = callback
      return Promise.resolve('watcher-1')
    })
    const { result } = renderHook(() => useBackgroundLocation())

    await act(async () => {
      await result.current.start()
    })
    act(() => {
      capturedCallback(null, { code: 'NOT_AUTHORIZED' })
    })

    expect(result.current.error).toBe('NOT_AUTHORIZED')
    expect(result.current.pingCount).toBe(0)
  })

  it('stop() calls removeWatcher and flips isTracking to false', async () => {
    addWatcherMock.mockResolvedValue('watcher-1')
    removeWatcherMock.mockResolvedValue(undefined)
    const { result } = renderHook(() => useBackgroundLocation())

    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      await result.current.stop()
    })

    expect(removeWatcherMock).toHaveBeenCalledWith({ id: 'watcher-1' })
    expect(result.current.isTracking).toBe(false)
  })
})
