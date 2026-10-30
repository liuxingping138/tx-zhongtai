import { describe, expect, it } from 'vitest'

import { createTurns } from './inTurn'

describe('createTurns', () => {
  it('后一个等前一个结束才开始，前一个失败也不挡住后一个', async () => {
    const inTurn = createTurns()
    const order: string[] = []
    let release!: () => void
    const first = inTurn(() => new Promise<void>((resolve) => { release = resolve }).then(() => { order.push('first') }))
    const failing = inTurn(() => { order.push('second'); return Promise.reject(new Error('409')) })
    const third = inTurn(() => { order.push('third'); return Promise.resolve() })
    await Promise.resolve()
    expect(order).toEqual([])
    release()
    await first
    await expect(failing).rejects.toThrow('409')
    await third
    expect(order).toEqual(['first', 'second', 'third'])
  })
})
