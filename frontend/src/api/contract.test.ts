import { describe, expect, it, vi } from 'vitest'

import auditSpec from '../../../docs/openapi/audit.json'
import codebookSpec from '../../../docs/openapi/codebook.json'
import iamSpec from '../../../docs/openapi/iam.json'
import policySpec from '../../../docs/openapi/policy.json'

const calls = vi.hoisted(() => [] as { method: string; url: string }[])
vi.mock('./http', () => {
  const record = (method: string) => (url: string) => {
    calls.push({ method, url })
    return Promise.resolve({ headers: {}, data: new Blob() })
  }
  return {
    http: { get: record('get'), post: record('post'), put: record('put'), patch: record('patch'), delete: record('delete') },
    request: (promise: Promise<unknown>) => promise.then(() => ({ items: [], total: 0 })),
  }
})
vi.mock('./excelImport', () => ({
  postExcelImport: (url: string) => {
    calls.push({ method: 'post', url })
    return Promise.resolve({})
  },
}))

import * as audit from './audit'
import * as auth from './auth'
import * as codebook from './codebook'
import * as crawler from './crawlerMonitoringV2'
import * as policy from './policy'
import * as scheduler from './scheduler'
import * as system from './system'

type Spec = { paths: Record<string, Record<string, unknown>> }

const operations = [auditSpec, codebookSpec, iamSpec, policySpec].flatMap((spec) =>
  Object.entries((spec as Spec).paths).flatMap(([path, methods]) =>
    Object.keys(methods).map((method) => ({
      method,
      pattern: new RegExp(`^${path.replace(/\{[^}]+\}/g, '[^/]+')}$`),
    })),
  ),
)

const modules = { audit, auth, codebook, crawler, policy, scheduler, system }

const wrappers = Object.entries(modules).flatMap(([module, exports]) =>
  Object.entries(exports)
    .filter((entry): entry is [string, (...args: unknown[]) => Promise<unknown>] => typeof entry[1] === 'function')
    .map(([name, fn]) => ({ label: `${module}.${name}`, fn })),
)

describe('前端接口封装与后端 OpenAPI 一致', () => {
  it.each(wrappers)('$label 调用的方法和路径在后端存在', async ({ fn }) => {
    calls.length = 0
    await fn('id-1', () => Promise.resolve({}))
    expect(calls.length).toBeGreaterThan(0)
    for (const { method, url } of calls) {
      const path = `/api/v1${url}`
      expect(operations.some((op) => op.method === method && op.pattern.test(path)), `${method.toUpperCase()} ${path}`).toBe(true)
    }
  })
})
