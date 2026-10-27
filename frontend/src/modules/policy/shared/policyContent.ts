/** 政策正文在详情里的摆法：按段落显示，先给前几段，「展开全文」再放开。正文本身由后端按源政策 ID 现读源库。 */
export const PREVIEW_PARAGRAPHS = 8

export function paragraphs(text: string): string[] {
  return text.split('\n').map(part => part.trim()).filter(Boolean)
}

export function shownParagraphs(parts: string[], expanded: boolean): string[] {
  return expanded || parts.length <= PREVIEW_PARAGRAPHS ? parts : parts.slice(0, PREVIEW_PARAGRAPHS)
}
