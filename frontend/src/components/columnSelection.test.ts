import { describe, expect, it } from 'vitest'

import { restoreColumns } from './columnSelection'

const CURRENT = ['name', 'plan', 'status', 'cost', 'watermark']

describe('列设置的记忆', () => {
  it('用户隐藏的列继续隐藏，页面上新加的列默认显示', () => {
    expect(restoreColumns(['name', 'status'], ['name', 'status', 'watermark'], CURRENT)).toEqual(['name', 'plan', 'status', 'cost'])
  })

  it('没有列清单的旧记录：分不清隐藏的和后加的，没记着的列都显示出来', () => {
    const old = ['name', 'enabled', 'daily_time', 'status', 'finished_at', 'watermark', 'next_run_at']
    expect(restoreColumns(old, null, CURRENT)).toEqual(CURRENT)
    expect(restoreColumns(['name', 'status'], null, CURRENT)).toEqual(CURRENT)
  })

  it('按页面列顺序返回；没记过或记的全不认识时交给默认值', () => {
    expect(restoreColumns(['watermark', 'name'], CURRENT, CURRENT)).toEqual(['name', 'watermark'])
    expect(restoreColumns(null, null, CURRENT)).toBeNull()
    expect(restoreColumns([], CURRENT, CURRENT)).toBeNull()
  })
})
