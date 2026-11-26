/** 保留原始 HTML；剥离脚本/元标签并由无权限 iframe + CSP 阻止外部内容访问平台。动态读取主题变量，随明暗主题切换。 */
function readToken(name: string, fallback: string, style?: Pick<CSSStyleDeclaration, 'getPropertyValue'>): string {
  const source = style ?? (typeof document !== 'undefined' && typeof getComputedStyle === 'function'
    ? getComputedStyle(document.documentElement)
    : undefined)
  return source?.getPropertyValue(name).trim() || fallback
}

export function sanitizeRawHtml(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, '')
    .replace(/<(?:script|meta|base)\b[^>]*\/?>/gi, '')
}

export function isolatedHtml(
  html: string,
  dark = false,
  style?: Pick<CSSStyleDeclaration, 'getPropertyValue'>,
): string {
  void dark
  const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'"
  const bg = readToken('--zt-panel', 'Canvas', style)
  const ink = readToken('--zt-ink-900', 'CanvasText', style)
  const link = readToken('--zt-blue-600', 'LinkText', style)
  const border = readToken('--zt-border-strong', 'GrayText', style)
  const thBg = readToken('--zt-table-head', 'Canvas', style)
  const sanitized = sanitizeRawHtml(html)
  const defaultStyles = `
    html, body {
      background-color: ${bg} !important;
      color: ${ink} !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
      font-size: 14px !important;
      line-height: 1.65 !important;
      margin: 0 !important;
      padding: 24px !important;
      word-break: break-word !important;
      box-sizing: border-box !important;
    }
    a { color: ${link} !important; text-decoration: underline !important; }
    table { border-collapse: collapse !important; max-width: 100% !important; margin: 12px 0 !important; }
    th, td { border: 1px solid ${border} !important; padding: 8px 12px !important; text-align: left !important; }
    th { background-color: ${thBg} !important; font-weight: 600 !important; }
    img { max-width: 100% !important; height: auto !important; }
  `.replace(/\s+/g, ' ').trim()
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="Content-Security-Policy" content="${policy}"><style>${defaultStyles}</style></head><body>${sanitized}</body></html>`
}
