import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/csrf', route => route.fulfill({ json: { data: { csrf_token: 'test' } } }))
  await page.route('**/api/v1/auth/refresh', route => route.fulfill({ status: 401, json: { message: '未登录' } }))
})

test('empty fields show inline errors and focus the first missing field', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByLabel('用户名', { exact: true })).toBeFocused()
  await expect(page.getByText('请输入用户名', { exact: true })).toBeVisible()
  await expect(page.getByText('请输入密码', { exact: true })).toBeVisible()
  await page.getByLabel('用户名', { exact: true }).fill('admin')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByLabel('密码', { exact: true })).toBeFocused()
})

test('password visibility, Enter submission, duplicate prevention and persistent error feedback', async ({ page }) => {
  let finish: (() => Promise<void>) | undefined
  let calls = 0
  await page.route('**/api/v1/auth/login', async route => {
    calls += 1
    finish = () => route.fulfill({ status: 401, json: { code: 'INVALID_CREDENTIALS', message: '用户名或密码错误' } })
  })
  await page.goto('/login')
  await page.getByLabel('用户名', { exact: true }).fill('admin')
  const password = page.getByLabel('密码', { exact: true })
  await password.fill('test-password')
  await page.getByRole('button', { name: '显示密码', exact: true }).click()
  await expect(password).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: '隐藏密码', exact: true }).click()
  await expect(password).toHaveAttribute('type', 'password')
  await password.press('Enter')
  await expect(page.getByRole('button', { name: '正在登录…', exact: true })).toBeDisabled()
  await expect.poll(() => calls).toBe(1)
  await finish!()
  await expect(page.getByRole('alert')).toHaveText('用户名或密码错误')
  await expect(password).toHaveValue('test-password')
  await password.fill('corrected')
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('mobile layout fits viewport with all login controls accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/login')
  await expect(page.getByLabel('用户名', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '登录', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
