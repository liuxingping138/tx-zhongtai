import { describe, expect, it } from 'vitest'

import { foldUnchanged, lineDiff } from './lineDiff'

describe('提示词按行比较', () => {
  it('标出删掉和新增的行，没变的保留', () => {
    expect(lineDiff('甲\n乙\n丙', '甲\n丁\n丙\n戊')).toEqual([
      { kind: 'same', text: '甲' },
      { kind: 'del', text: '乙' },
      { kind: 'add', text: '丁' },
      { kind: 'same', text: '丙' },
      { kind: 'add', text: '戊' },
    ])
  })

  it('完全一样时全是 same', () => {
    expect(lineDiff('a\nb', 'a\nb').every(line => line.kind === 'same')).toBe(true)
  })

  it('没变的长段折叠，只留改动上下文', () => {
    const before = Array.from({ length: 12 }, (_, index) => `第${index}行`).join('\n')
    const after = before.replace('第6行', '第6行改')
    const blocks = foldUnchanged(lineDiff(before, after), 1)
    expect(blocks).toEqual([
      { kind: 'fold', count: 5 },
      { kind: 'same', text: '第5行' },
      { kind: 'del', text: '第6行' },
      { kind: 'add', text: '第6行改' },
      { kind: 'same', text: '第7行' },
      { kind: 'fold', count: 4 },
    ])
  })
})
