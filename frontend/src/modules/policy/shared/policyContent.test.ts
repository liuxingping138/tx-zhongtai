import { describe, expect, it } from 'vitest'

import { PREVIEW_PARAGRAPHS, paragraphs, shownParagraphs } from './policyContent'

describe('政策正文的段落', () => {
  it('按换行分段，空行和首尾空白去掉', () => {
    expect(paragraphs(' 第一段 \n\n第二段\n  \n')).toEqual(['第一段', '第二段'])
  })

  it('长正文先给前几段，展开后全给；短正文不折叠', () => {
    const long = Array.from({ length: PREVIEW_PARAGRAPHS + 3 }, (_, index) => `第 ${index + 1} 段`)
    expect(shownParagraphs(long, false)).toHaveLength(PREVIEW_PARAGRAPHS)
    expect(shownParagraphs(long, true)).toHaveLength(PREVIEW_PARAGRAPHS + 3)
    expect(shownParagraphs(['仅一段'], false)).toEqual(['仅一段'])
  })
})
