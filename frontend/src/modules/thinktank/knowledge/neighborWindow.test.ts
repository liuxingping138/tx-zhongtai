import { describe, expect, it } from 'vitest'

import { fetchNeighbors, neighborWindow } from './neighborWindow'

describe('neighborWindow', () => {
  it('covers position - 1, position, and position + 1 in a single page for positions 0..500', () => {
    for (let pos = 0; pos <= 500; pos += 1) {
      const win = neighborWindow(pos)
      expect(win).not.toBeNull()
      if (!win) continue
      const start = (win.page - 1) * win.size
      expect(start + win.localIndex).toBe(pos)
      if (pos > 0) {
        expect(win.localIndex).toBeGreaterThanOrEqual(1)
        expect(start + win.localIndex - 1).toBe(pos - 1)
      }
      expect(win.localIndex + 1).toBeLessThan(win.size)
      expect(start + win.localIndex + 1).toBe(pos + 1)
    }
  })

  it('returns null for negative or non-integer positions', () => {
    expect(neighborWindow(-1)).toBeNull()
    expect(neighborWindow(1.5)).toBeNull()
  })

  it('fetches exact previous and next ids for first, middle, and last positions', async () => {
    const all = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }, { id: 'e' }]
    const fetchPage = (page: number, pageSize: number) => {
      const start = (page - 1) * pageSize
      return Promise.resolve({ total: all.length, items: all.slice(start, start + pageSize) })
    }
    expect(await fetchNeighbors(0, fetchPage)).toEqual({ total: 5, prevId: null, nextId: 'b' })
    expect(await fetchNeighbors(1, fetchPage)).toEqual({ total: 5, prevId: 'a', nextId: 'c' })
    expect(await fetchNeighbors(2, fetchPage)).toEqual({ total: 5, prevId: 'b', nextId: 'd' })
    expect(await fetchNeighbors(4, fetchPage)).toEqual({ total: 5, prevId: 'd', nextId: null })
  })
})
