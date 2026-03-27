// Task 6 / Task 9 — E2E: Full happy-path flow for both input modes (all backend mocked)
const { test, expect } = require('@playwright/test')
const path = require('path')

const SCREENSHOTS = path.resolve(__dirname, '../screenshots')

const PDF_CONTENT = Buffer.from(
  '%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
)

const NOTEBOOK_JSON = JSON.stringify({
  nbformat: 4,
  nbformat_minor: 5,
  metadata: { kernelspec: { name: 'python3', display_name: 'Python 3', language: 'python' } },
  cells: [
    { cell_type: 'markdown', metadata: {}, source: ['# Attention Is All You Need'] },
    { cell_type: 'code',     metadata: {}, source: ['import torch\nimport numpy as np'] },
  ],
})
const NOTEBOOK_B64 = Buffer.from(NOTEBOOK_JSON).toString('base64')

const ALL_PHASES = [
  { phase: 'parsing',    message: 'Parsing PDF and extracting text...' },
  { phase: 'analyzing',  message: 'Identifying algorithms...' },
  { phase: 'generating', message: 'Generating implementation...' },
  { phase: 'assembling', message: 'Assembling notebook cells...' },
  { phase: 'done',       message: 'Done! Your notebook is ready.', notebook_b64: NOTEBOOK_B64 },
]

// Inject a JS mock for EventSource so SSE works reliably in headless mode.
async function mockEventSource(page, events) {
  await page.addInitScript((eventsJson) => {
    const events = JSON.parse(eventsJson)
    window.EventSource = class MockEventSource {
      constructor(_url) {
        this.readyState = 1
        this._closed = false
        this.onmessage = null
        this.onerror = null
        let i = 0
        const tick = () => {
          if (this._closed || i >= events.length) return
          const ev = events[i++]
          if (this.onmessage) this.onmessage({ data: JSON.stringify(ev) })
          if (!this._closed) setTimeout(tick, 15)
        }
        setTimeout(tick, 30)
      }
      close() { this._closed = true; this.readyState = 2 }
      addEventListener() {}
      removeEventListener() {}
    }
  }, JSON.stringify(events))
}

async function mockGenerate(page, jobId = 'job-full-flow') {
  await page.route('**/generate', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ job_id: jobId }),
    })
  })
}

// ── Full-flow tests ───────────────────────────────────────────────────────────

test.describe('Task 9 — Full happy-path flows (mocked backend)', () => {

  test('task9-01: upload mode full flow shows all phase messages then done', async ({ page }) => {
    await mockEventSource(page, ALL_PHASES)
    await mockGenerate(page)
    await page.goto('/')
    await page.screenshot({ path: `${SCREENSHOTS}/task9-01-initial.png`, fullPage: true })

    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByTestId('progress-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Parsing PDF and extracting text...')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Generating implementation...')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Done! Your notebook is ready.')).toBeVisible({ timeout: 5000 })

    await page.screenshot({ path: `${SCREENSHOTS}/task9-01-done.png`, fullPage: true })
  })

  test('task9-02: arXiv URL mode full flow shows progress panel', async ({ page }) => {
    await mockEventSource(page, ALL_PHASES)
    await mockGenerate(page)
    await page.goto('/')

    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('tab-arxiv').click()
    await page.getByTestId('arxiv-url-input').fill('https://arxiv.org/abs/1706.03762')

    await page.screenshot({ path: `${SCREENSHOTS}/task9-02-arxiv-ready.png` })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByTestId('progress-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Done! Your notebook is ready.')).toBeVisible({ timeout: 5000 })

    await page.screenshot({ path: `${SCREENSHOTS}/task9-02-arxiv-done.png`, fullPage: true })
  })

  test('task9-03: arXiv URL is included in POST body when submitting arXiv mode', async ({ page }) => {
    await mockEventSource(page, [{ phase: 'error', message: 'test-stop' }])
    let capturedBody = null
    await page.route('**/generate', async (route) => {
      capturedBody = route.request().postData()
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ job_id: 'j1' }) })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('tab-arxiv').click()
    await page.getByTestId('arxiv-url-input').fill('https://arxiv.org/abs/1706.03762')
    await page.getByTestId('generate-btn').click()

    await page.waitForTimeout(200)
    await page.screenshot({ path: `${SCREENSHOTS}/task9-03-arxiv-post.png` })

    expect(capturedBody).toContain('arxiv_url')
    expect(capturedBody).toContain('1706.03762')
    expect(capturedBody).not.toContain('pdf_file')
  })

  test('task9-04: upload mode sends pdf_file NOT arxiv_url', async ({ page }) => {
    await mockEventSource(page, [{ phase: 'error', message: 'test-stop' }])
    let capturedBody = null
    await page.route('**/generate', async (route) => {
      capturedBody = route.request().postData()
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ job_id: 'j2' }) })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    // default tab is upload
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await page.waitForTimeout(200)
    await page.screenshot({ path: `${SCREENSHOTS}/task9-04-upload-post.png` })

    expect(capturedBody).toContain('pdf_file')
  })

  test('task9-05: done event triggers notebook download', async ({ page }) => {
    await mockEventSource(page, [
      { phase: 'done', message: 'Done!', notebook_b64: NOTEBOOK_B64 },
    ])
    await mockGenerate(page)

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })

    // Wait for the download event to fire
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 8000 }),
      page.getByTestId('generate-btn').click(),
    ])

    expect(download.suggestedFilename()).toBe('notebook.ipynb')
    await page.screenshot({ path: `${SCREENSHOTS}/task9-05-download-triggered.png`, fullPage: true })
  })

  test('task9-06: error SSE event shows error message and re-shows form', async ({ page }) => {
    await mockEventSource(page, [
      { phase: 'parsing', message: 'Parsing...' },
      { phase: 'error',   message: 'APIError: model quota exceeded' },
    ])
    await mockGenerate(page)

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-bad-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByTestId('form-card')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText(/quota exceeded/i)).toBeVisible({ timeout: 5000 })
    await page.screenshot({ path: `${SCREENSHOTS}/task9-06-error-reshow-form.png`, fullPage: true })
  })

  test('task9-07: colab_url from done event renders Open in Colab link', async ({ page }) => {
    const COLAB = 'https://colab.research.google.com/gist/user/abc123'
    await mockEventSource(page, [
      { phase: 'done', message: 'Done!', notebook_b64: NOTEBOOK_B64, colab_url: COLAB },
    ])
    await mockGenerate(page)

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    const link = page.getByRole('link', { name: /open in colab/i })
    await expect(link).toBeVisible({ timeout: 5000 })
    expect(await link.getAttribute('href')).toBe(COLAB)
    expect(await link.getAttribute('target')).toBe('_blank')
    await page.screenshot({ path: `${SCREENSHOTS}/task9-07-colab-link.png`, fullPage: true })
  })

  test('task9-08: unsafe colab_url is silently dropped (no link rendered)', async ({ page }) => {
    await mockEventSource(page, [
      { phase: 'done', message: 'Done! Your notebook is ready.', notebook_b64: NOTEBOOK_B64,
        colab_url: 'https://evil.com/colab.research.google.com/' },
    ])
    await mockGenerate(page)

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByText('Done! Your notebook is ready.')).toBeVisible({ timeout: 5000 })
    // Unsafe colab URL must NOT produce a link
    const colabLink = page.getByRole('link', { name: /open in colab/i })
    await expect(colabLink).toHaveCount(0)
    await page.screenshot({ path: `${SCREENSHOTS}/task9-08-unsafe-colab-dropped.png`, fullPage: true })
  })

  test('task9-09: /generate 422 shows error without crashing the app', async ({ page }) => {
    await page.route('**/generate', async (route) => {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Provide either a pdf_file or an arxiv_url.' }),
      })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('AIza-test-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByTestId('form-card')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText(/422|server error/i)).toBeVisible({ timeout: 5000 })
    await page.screenshot({ path: `${SCREENSHOTS}/task9-09-422-error.png`, fullPage: true })
  })
})
