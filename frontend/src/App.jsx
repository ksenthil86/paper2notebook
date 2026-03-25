import { useState, useCallback } from 'react'
import './App.css'

const PHASES = [
  { key: 'parsing',    label: 'Parsing PDF' },
  { key: 'analyzing',  label: 'Analyzing paper' },
  { key: 'generating', label: 'Generating notebook' },
  { key: 'assembling', label: 'Assembling cells' },
  { key: 'uploading',  label: 'Uploading to Gist' },
]

export default function App() {
  const [apiKey, setApiKey] = useState('')
  const [githubToken, setGithubToken] = useState('')
  const [githubOpen, setGithubOpen] = useState(false)
  const [pdfFile, setPdfFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState(null) // null = hidden, array = visible
  const [error, setError] = useState(null)

  const canGenerate = apiKey.trim().length > 0 && pdfFile !== null

  // ── File selection ──────────────────────────────────
  const handleFileChange = useCallback((e) => {
    const file = e.target.files?.[0]
    if (file) setPdfFile(file)
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) setPdfFile(file)
  }, [])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDragOver(false)
  }, [])

  // ── Submit ──────────────────────────────────────────
  const handleSubmit = useCallback(async (e) => {
    e.preventDefault()
    if (!canGenerate) return

    setError(null)
    setProgress([])

    const formData = new FormData()
    formData.append('api_key', apiKey)
    formData.append('pdf_file', pdfFile)
    if (githubToken.trim()) formData.append('github_token', githubToken.trim())

    let jobId
    try {
      const res = await fetch('/generate', { method: 'POST', body: formData })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      jobId = data.job_id
    } catch (err) {
      setProgress(null)
      setError(`Failed to start: ${err.message}`)
      return
    }

    const es = new EventSource(`/status/${jobId}`)
    let streamDone = false

    es.onmessage = (ev) => {
      const event = JSON.parse(ev.data)
      const { phase, message, notebook_b64, colab_url } = event

      if (phase === 'done') {
        streamDone = true
        es.close()
        setProgress((prev) => [...(prev || []), { phase, message, done: true }])
        if (notebook_b64) {
          const blob = new Blob([Uint8Array.from(atob(notebook_b64), (c) => c.charCodeAt(0))], {
            type: 'application/json',
          })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = 'notebook.ipynb'
          a.click()
          URL.revokeObjectURL(url)
        }
        if (colab_url) {
          setProgress((prev) => [...(prev || []), { phase: 'colab', colab_url }])
        }
      } else if (phase === 'error') {
        streamDone = true
        es.close()
        setProgress(null)
        setError(message)
      } else {
        setProgress((prev) => [...(prev || []), { phase, message }])
      }
    }
    es.onerror = () => {
      if (streamDone) return
      streamDone = true
      es.close()
      setProgress(null)
      setError('Connection lost. Please try again.')
    }
  }, [apiKey, pdfFile, githubToken, canGenerate])

  return (
    <div data-testid="app-root">
      <header className="header">
        <h1 className="app-title" data-testid="app-title">
          <span>Paper</span>2Notebook
        </h1>
        <p className="app-tagline">
          Upload a research paper PDF — get a production-quality Colab notebook.
        </p>
      </header>

      {progress === null ? (
        <form
          className="form-card"
          data-testid="form-card"
          onSubmit={handleSubmit}
        >
          {/* API key */}
          <div className="field-group">
            <label className="field-label" htmlFor="api-key-input">
              Gemini API Key
            </label>
            <input
              id="api-key-input"
              data-testid="api-key-input"
              type="password"
              className="input"
              placeholder="AIza..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          {/* GitHub token (collapsible) */}
          <div className="field-group">
            <button
              type="button"
              className={`collapsible-toggle${githubOpen ? ' open' : ''}`}
              data-testid="github-token-toggle"
              onClick={() => setGithubOpen((o) => !o)}
            >
              <span className="chevron">▶</span>
              Optional — for Open in Colab
            </button>
            <div className={`collapsible-body${githubOpen ? ' open' : ''}`}>
              <input
                data-testid="github-token-input"
                type="password"
                className="input"
                placeholder="ghp_..."
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              <p className="hint">
                A GitHub personal access token with gist scope lets us upload your notebook
                so you can open it directly in Google Colab.
              </p>
            </div>
          </div>

          {/* PDF drop zone */}
          <div className="field-group">
            <label className="field-label">Research Paper (PDF)</label>
            <div
              className={`dropzone${dragOver ? ' drag-over' : ''}`}
              data-testid="pdf-dropzone"
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <input
                data-testid="pdf-file-input"
                type="file"
                accept=".pdf,application/pdf"
                className="file-input-hidden"
                onChange={handleFileChange}
              />
              {pdfFile ? (
                <span className="dropzone-filename">📄 {pdfFile.name}</span>
              ) : (
                <>
                  <span className="dropzone-icon">📄</span>
                  <span className="dropzone-text">
                    Drop your PDF here or <strong>click to browse</strong>
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Generate button */}
          <button
            type="submit"
            className="generate-btn"
            data-testid="generate-btn"
            disabled={!canGenerate}
          >
            Generate Notebook
          </button>

          {error && <p className="error-msg">{error}</p>}
        </form>
      ) : (
        <div className="progress-panel" data-testid="progress-panel">
          <p className="progress-title">Generating your notebook…</p>
          <ul className="progress-list">
            {progress.map((ev, i) => {
              if (ev.phase === 'colab') {
                return (
                  <li key={i} className="progress-item">
                    <span className="progress-icon">🔗</span>
                    <span className="progress-message">
                      <a href={ev.colab_url} target="_blank" rel="noopener noreferrer">
                        Open in Colab ↗
                      </a>
                    </span>
                  </li>
                )
              }
              const isDone = ev.done
              return (
                <li key={i} className={`progress-item${isDone ? ' done' : ''}`}>
                  <span className="progress-icon">
                    {isDone ? (
                      <span className="checkmark">✓</span>
                    ) : i === progress.length - 1 ? (
                      <span className="spinner" />
                    ) : (
                      <span className="checkmark">✓</span>
                    )}
                  </span>
                  <span className="progress-message">{ev.message}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
