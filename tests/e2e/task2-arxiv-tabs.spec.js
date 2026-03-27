// Task 2 — E2E tests: arXiv URL input mode tab toggle
const { test, expect } = require('@playwright/test')
const path = require('path')

const SCREENSHOTS = path.resolve(__dirname, '../screenshots')

test.describe('Task 2 — arXiv URL input mode', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('task2-01: input-mode-tabs element is present', async ({ page }) => {
    await page.screenshot({ path: `${SCREENSHOTS}/task2-01-initial.png`, fullPage: true })
    await expect(page.getByTestId('input-mode-tabs')).toBeVisible()
  })

  test('task2-02: upload mode is the default active tab', async ({ page }) => {
    const tabs = page.getByTestId('input-mode-tabs')
    await expect(tabs).toBeVisible()
    // File input should be visible in default (upload) mode
    await expect(page.getByTestId('pdf-dropzone')).toBeVisible()
    await page.screenshot({ path: `${SCREENSHOTS}/task2-02-upload-default.png` })
  })

  test('task2-03: clicking arXiv tab shows the URL input', async ({ page }) => {
    await page.getByTestId('tab-arxiv').click()
    await expect(page.getByTestId('arxiv-url-input')).toBeVisible()
    await page.screenshot({ path: `${SCREENSHOTS}/task2-03-arxiv-tab-active.png` })
  })

  test('task2-04: arXiv mode hides the PDF drop zone', async ({ page }) => {
    await page.getByTestId('tab-arxiv').click()
    await expect(page.getByTestId('pdf-dropzone')).not.toBeVisible()
    await page.screenshot({ path: `${SCREENSHOTS}/task2-04-dropzone-hidden.png` })
  })

  test('task2-05: switching back to upload tab shows dropzone again', async ({ page }) => {
    await page.getByTestId('tab-arxiv').click()
    await expect(page.getByTestId('pdf-dropzone')).not.toBeVisible()
    await page.getByTestId('tab-upload').click()
    await expect(page.getByTestId('pdf-dropzone')).toBeVisible()
    await page.screenshot({ path: `${SCREENSHOTS}/task2-05-back-to-upload.png` })
  })

  test('task2-06: generate button enables after typing arXiv URL + API key', async ({ page }) => {
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('tab-arxiv').click()
    const btn = page.getByTestId('generate-btn')
    await expect(btn).toBeDisabled()
    await page.getByTestId('arxiv-url-input').fill('https://arxiv.org/abs/1706.03762')
    await expect(btn).toBeEnabled({ timeout: 2000 })
    await page.screenshot({ path: `${SCREENSHOTS}/task2-06-arxiv-btn-enabled.png` })
  })

  test('task2-07: generate button stays disabled with empty arXiv URL', async ({ page }) => {
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('tab-arxiv').click()
    const btn = page.getByTestId('generate-btn')
    await expect(btn).toBeDisabled()
    await page.screenshot({ path: `${SCREENSHOTS}/task2-07-arxiv-btn-disabled.png` })
  })

  test('task2-08: arXiv URL is sent as form field when submitting', async ({ page }) => {
    let capturedBody = null
    await page.route('/generate', async (route) => {
      capturedBody = route.request().postData()
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ job_id: 'test-123' }) })
    })
    await page.route('/status/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'data: {"phase":"error","message":"test"}\n\n',
      })
    })

    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('tab-arxiv').click()
    await page.getByTestId('arxiv-url-input').fill('https://arxiv.org/abs/1706.03762')
    await page.getByTestId('generate-btn').click()

    await page.waitForTimeout(300)
    await page.screenshot({ path: `${SCREENSHOTS}/task2-08-arxiv-submitted.png` })
    expect(capturedBody).toContain('arxiv_url')
    expect(capturedBody).toContain('1706.03762')
  })
})
