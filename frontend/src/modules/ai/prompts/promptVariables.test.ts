import { describe, expect, it } from 'vitest'

import { promptSegments, unusedColumns, usedVariables, variableState } from './promptVariables'

const HEADERS = ['政策标题', '政策正文']

describe('提示词变量', () => {
  it('按能否替换分：Excel 列、码表、找不到、没选码表；还没传样本的列名先不算错', () => {
    expect(variableState('政策标题', HEADERS, false)).toBe('column')
    expect(variableState('上传码表', HEADERS, true)).toBe('code')
    expect(variableState('上传码表', HEADERS, false)).toBe('nocode')
    expect(variableState('政策名称', HEADERS, true)).toBe('missing')
    expect(variableState('政策名称', [], true)).toBe('pending')
    expect(variableState('上传码表', [], true)).toBe('code')
  })

  it('切出变量片段，拼回去和原文一字不差', () => {
    const text = '标题：@【政策标题】\n正文：@【政策正文】，参考 @【上传码表】 和 @【不存在】'
    const segments = promptSegments(text, HEADERS, true)
    expect(segments.map(item => item.text).join('')).toBe(text)
    expect(segments.filter(item => item.state).map(item => [item.text, item.state])).toEqual([
      ['@【政策标题】', 'column'],
      ['@【政策正文】', 'column'],
      ['@【上传码表】', 'code'],
      ['@【不存在】', 'missing'],
    ])
    expect(promptSegments('', HEADERS, false)).toEqual([])
  })

  it('列出用到的变量和还没用的列', () => {
    const text = '@【政策标题】 @【政策标题】 @【地区】'
    expect(usedVariables(text, HEADERS, false)).toEqual([
      { name: '政策标题', state: 'column', count: 2 },
      { name: '地区', state: 'missing', count: 1 },
    ])
    expect(unusedColumns(text, HEADERS)).toEqual(['政策正文'])
  })
})

describe('和后端同一套变量规则', () => {
  it('列名去掉首尾空白，跨行、带「【」的也算一个变量（后端就是这么替换的）', () => {
    const headers = ['政策正文']
    expect(usedVariables('看 @【 政策正文 】', headers, false)).toEqual([{ name: '政策正文', state: 'column', count: 1 }])
    expect(usedVariables('看 @【政策\n正文】', headers, false).map(item => item.state)).toEqual(['missing'])
    expect(usedVariables('看 @【政策【标题】', headers, false).map(item => item.name)).toEqual(['政策【标题'])
  })
})
