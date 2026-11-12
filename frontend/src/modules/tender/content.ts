/** 保留原始 HTML；无脚本/同源/表单权限的 iframe + CSP 阻止外部内容访问平台。注入公文阅读纸张底色与字体规范。 */
export function isolatedHtml(html: string): string {
  const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'"
  const defaultStyles = `
    html, body {
      background-color: #ffffff !important;
      color: #1e293b !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
      font-size: 14px !important;
      line-height: 1.65 !important;
      margin: 0 !important;
      padding: 20px 24px !important;
      word-break: break-word !important;
      box-sizing: border-box !important;
    }
    a { color: #1a73e8 !important; text-decoration: underline !important; }
    table { border-collapse: collapse !important; max-width: 100% !important; margin: 12px 0 !important; }
    th, td { border: 1px solid #cbd5e1 !important; padding: 8px 12px !important; text-align: left !important; }
    th { background-color: #f1f5f9 !important; font-weight: 600 !important; }
    img { max-width: 100% !important; height: auto !important; }
  `.replace(/\s+/g, ' ').trim()
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="Content-Security-Policy" content="${policy}"><style>${defaultStyles}</style></head><body>${html}</body></html>`
}
