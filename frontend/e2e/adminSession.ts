import { expect, type Page } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

/** 首次登录改密后的口令后缀。globalSetup 与页面登录共用，避免并行用例各改一次。 */
export const changedPasswordSuffix = 'Aa1'

export const adminPasswordFile = path.join(import.meta.dirname, '.admin-password')

export function currentAdminPassword(): string {
  if (existsSync(adminPasswordFile)) return readFileSync(adminPasswordFile, 'utf8').trim()
  return process.env.ADMIN_PASSWORD || ''
}

/** 登录隔离环境管理员。新账号会先停在改密页，保存后才进入工作台。 */
export async function loginAdmin(page: Page, redirect?: string): Promise<void> {
  const password = currentAdminPassword()
  const username = process.env.ADMIN_USERNAME || 'p6admin'
  const next = password + changedPasswordSuffix
  await page.goto(redirect ? `/login?redirect=${encodeURIComponent(redirect)}` : '/login')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  const nav = page.getByRole('navigation', { name: '一级模块' })
  const change = page.getByRole('heading', { name: '首次登录请修改密码' })
  await expect(nav.or(change)).toBeVisible({ timeout: 20_000 })
  if (await change.isVisible()) {
    await page.getByRole('textbox', { name: /原密码/ }).fill(password)
    await page.getByRole('textbox', { name: /^\*?新密码$/ }).fill(next)
    await page.getByRole('textbox', { name: /确认新密码/ }).fill(next)
    await page.getByRole('button', { name: '保存并进入系统' }).click()
  }
  await expect(nav).toBeVisible({ timeout: 20_000 })
}
