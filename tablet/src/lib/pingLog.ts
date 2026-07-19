const STORAGE_KEY = 'ff_spike_pings'

export interface PingLogEntry {
  latitude: number
  longitude: number
  accuracy: number
  time: number
}

export function getPings(): PingLogEntry[] {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return []
  return JSON.parse(raw) as PingLogEntry[]
}

export function appendPing(entry: PingLogEntry): void {
  const pings = getPings()
  pings.push(entry)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pings))
}

export function clearPings(): void {
  localStorage.removeItem(STORAGE_KEY)
}
