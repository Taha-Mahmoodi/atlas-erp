import { describe, it, expect, beforeEach } from 'vitest'
import { appendPing, getPings, clearPings } from './pingLog'

describe('pingLog', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns an empty array when no pings have been logged', () => {
    expect(getPings()).toEqual([])
  })

  it('appends a ping and returns it from getPings', () => {
    appendPing({ latitude: 1.5, longitude: 2.5, accuracy: 10, time: 1000 })
    expect(getPings()).toEqual([{ latitude: 1.5, longitude: 2.5, accuracy: 10, time: 1000 }])
  })

  it('appends multiple pings in order, oldest first', () => {
    appendPing({ latitude: 1, longitude: 1, accuracy: 5, time: 100 })
    appendPing({ latitude: 2, longitude: 2, accuracy: 5, time: 200 })
    expect(getPings().map((p) => p.time)).toEqual([100, 200])
  })

  it('persists across separate reads (survives "app restart")', () => {
    appendPing({ latitude: 1, longitude: 1, accuracy: 5, time: 100 })
    expect(getPings()).toHaveLength(1)
    expect(getPings()).toHaveLength(1) // second independent read, same storage
  })

  it('clearPings empties the log', () => {
    appendPing({ latitude: 1, longitude: 1, accuracy: 5, time: 100 })
    clearPings()
    expect(getPings()).toEqual([])
  })
})
