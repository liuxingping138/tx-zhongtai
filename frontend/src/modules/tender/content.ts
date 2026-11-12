/** 保留原始 HTML；无脚本/同源/表单权限的 iframe + CSP 阻止外部内容访问平台。 */
export function isolatedHtml(html: string): string {
  const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'"
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}"></head><body>${html}</body></html>`
}
