// Task 8 — E2E tests: frontend ↔ backend wiring (SSE, download, error handling)
const { test, expect } = require('@playwright/test')
const path = require('path')

const SCREENSHOTS = path.resolve(__dirname, '../screenshots')

// Helper: build a minimal valid PDF buffer
const PDF_CONTENT = Buffer.from(
  '%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
)

// Minimal base64-encoded notebook (valid JSON .ipynb)
const NOTEBOOK_JSON = JSON.stringify({
  nbformat: 4,
  nbformat_minor: 5,
  metadata: { kernelspec: { name: 'python3', display_name: 'Python 3', language: 'python' } },
  cells: [{ cell_type: 'markdown', metadata: {}, source: ['# Test Notebook'] }],
})
const NOTEBOOK_B64 = Buffer.from(NOTEBOOK_JSON).toString('base64')

// Inject a controllable EventSource mock into the page.
// Playwright's route.fulfill() for SSE fires onerror before onmessage,
// so we replace EventSource with a controlled JS implementation.
async function injectEventSourceMock(page, events) {
  await page.addInitScript((eventsJson) => {
    const events = JSON.parse(eventsJson)
    // Replace global EventSource with a mock that fires events in order
    window.EventSource = class MockEventSource {
      constructor(_url) {
        this.readyState = 1 // OPEN
        this._closed = false
        this.onmessage = null
        this.onerror = null
        // Dispatch events asynchronously so the app can set up handlers first
        let i = 0
        const tick = () => {
          if (this._closed || i >= events.length) return
          const ev = events[i++]
          if (this.onmessage) {
            this.onmessage({ data: JSON.stringify(ev) })
          }
          if (!this._closed) setTimeout(tick, 10)
        }
        setTimeout(tick, 20)
      }
      close() {
        this._closed = true
        this.readyState = 2 // CLOSED
      }
      addEventListener() {}
      removeEventListener() {}
    }
  }, JSON.stringify(events))
}

test.describe('Task 8 — Frontend ↔ Backend wiring', () => {

  test('task8-01: progress panel appears on submit with mocked SSE', async ({ page }) => {
    const events = [
      { phase: 'parsing', message: 'Parsing PDF...' },
      { phase: 'done', message: 'Done! Your notebook is ready.', notebook_b64: NOTEBOOK_B64 },
    ]
    await injectEventSourceMock(page, events)

    await page.route('**/generate', async (route) => {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'test-job-001' }),
      })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('sk-test-key-12345')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf',
      mimeType: 'application/pdf',
      buffer: PDF_CONTENT,
    })

    await page.getByTestId('generate-btn').click()

    // Progress panel should appear; form should be hidden
    await expect(page.getByTestId('progress-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.getByTestId('form-card')).toHaveCount(0)

    await page.screenshot({ path: `${SCREENSHOTS}/task8-01-progress-panel-visible.png`, fullPage: true })
  })

  test('task8-02: SSE events render phase messages in progress list', async ({ page }) => {
    const events = [
      { phase: 'parsing',    message: 'Parsing PDF and extracting text...' },
      { phase: 'analyzing',  message: 'Identifying algorithms...' },
      { phase: 'generating', message: 'Generating implementation...' },
      { phase: 'assembling', message: 'Assembling notebook cells...' },
      { phase: 'done',       message: 'Done! Your notebook is ready.', notebook_b64: NOTEBOOK_B64 },
    ]
    await injectEventSourceMock(page, events)

    await page.route('**/generate', async (route) => {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'test-job-002' }),
      })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('sk-test-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByTestId('progress-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Parsing PDF and extracting text...')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Done! Your notebook is ready.')).toBeVisible({ timeout: 5000 })

    await page.screenshot({ path: `${SCREENSHOTS}/task8-02-sse-messages.png`, fullPage: true })
  })

  test('task8-03: error event shows error message and re-enables form', async ({ page }) => {
    const events = [
      { phase: 'error', message: 'Generation failed: APIError: quota exceeded' },
    ]
    await injectEventSourceMock(page, events)

    await page.route('**/generate', async (route) => {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'test-job-003' }),
      })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('sk-bad-key')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    // Form should reappear after error
    await expect(page.getByTestId('form-card')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText(/quota exceeded/i)).toBeVisible({ timeout: 5000 })

    await page.screenshot({ path: `${SCREENSHOTS}/task8-03-error-message.png`, fullPage: true })
  })

  test('task8-04: colab_url in done event shows Open in Colab link', async ({ page }) => {
    const COLAB_URL = 'https://colab.research.google.com/gist/testuser/abc123'
    const events = [
      { phase: 'done', message: 'Done!', notebook_b64: NOTEBOOK_B64, colab_url: COLAB_URL },
    ]
    await injectEventSourceMock(page, events)

    await page.route('**/generate', async (route) => {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'test-job-004' }),
      })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('sk-test')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    await expect(page.getByText(/open in colab/i)).toBeVisible({ timeout: 5000 })
    const link = page.getByRole('link', { name: /open in colab/i })
    const href = await link.getAttribute('href')
    expect(href).toBe(COLAB_URL)
    const target = await link.getAttribute('target')
    expect(target).toBe('_blank')

    await page.screenshot({ path: `${SCREENSHOTS}/task8-04-colab-link.png`, fullPage: true })
  })

  test('task8-05: server 500 on /generate shows error without crashing', async ({ page }) => {
    await page.route('**/generate', async (route) => {
      await route.fulfill({ status: 500, body: 'Internal Server Error' })
    })

    await page.goto('/')
    await page.getByTestId('api-key-input').fill('sk-test')
    await page.getByTestId('pdf-file-input').setInputFiles({
      name: 'paper.pdf', mimeType: 'application/pdf', buffer: PDF_CONTENT,
    })
    await page.getByTestId('generate-btn').click()

    // Form card should remain visible (error re-enables form)
    await expect(page.getByTestId('form-card')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText(/server error/i)).toBeVisible({ timeout: 5000 })

    await page.screenshot({ path: `${SCREENSHOTS}/task8-05-server-error.png`, fullPage: true })
  })

})
