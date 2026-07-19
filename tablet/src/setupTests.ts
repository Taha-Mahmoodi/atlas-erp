import '@testing-library/jest-dom'

// ponytail: Node 22+ ships an experimental global `localStorage`/`sessionStorage`
// that throws without --localstorage-file. Vitest's jsdom environment only
// overrides globals already present on `global` if they're on its explicit
// allow-list (which localStorage/sessionStorage aren't in this vitest version),
// so Node's non-functional stub wins over jsdom's real implementation.
// Minimal in-memory Storage polyfill to unblock localStorage-dependent tests.
// Upgrade path: drop this once vitest's jsdom environment allow-lists these keys.
class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

for (const key of ['localStorage', 'sessionStorage'] as const) {
  Object.defineProperty(globalThis, key, {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  })
}
