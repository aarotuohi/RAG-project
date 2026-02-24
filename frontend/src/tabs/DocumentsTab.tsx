import { useState, useEffect } from 'react'

interface Props {
  status: {
    collection_counts: Record<string, number>
    recommended_model: string
    local_models: string[]
  } | null
  onRefresh: () => void
}

interface DocumentFiles {
  cost_history: string[]
  cvs: string[]
  contacts: string[]
  boilerplate: string[]
}

const CATEGORIES = [
  {
    key: 'cost_history',
    label: 'Cost History (Excel)',
    description: 'Historical project Excel files used to estimate hours and costs for new projects.',
    accepted: '.xlsx, .xls',
    reindexEndpoint: '/api/ingest/cost-history',
  },
  {
    key: 'cvs',
    label: 'Expert CVs',
    description: 'A combined CV file (.docx or .pdf) containing all expert profiles. The AI will select the best match per project.',
    accepted: '.docx, .pdf',
    reindexEndpoint: '/api/ingest/cvs',
  },
  {
    key: 'contacts',
    label: 'Salesperson Contacts',
    description: 'File containing salesperson names, emails, and phone numbers used in Section 10.',
    accepted: '.xlsx, .xls, .docx, .pdf',
    reindexEndpoint: null,
  },
  {
    key: 'boilerplate',
    label: 'Boilerplate / Terms',
    description: 'Static text files for Sections 6 (Documentation), 7 (Quality Assurance / SKOL), and 9 (Delivery Terms).',
    accepted: '.txt, .docx, .pdf',
    reindexEndpoint: '/api/ingest/boilerplate',
  },
]

export default function DocumentsTab({ status, onRefresh }: Props) {
  const [loading, setLoading] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [paths, setPaths] = useState<Record<string, string>>({})
  const [docFiles, setDocFiles] = useState<DocumentFiles | null>(null)
  const [pullModel, setPullModel] = useState('')

  const fetchDocFiles = () => {
    fetch('/api/documents')
      .then(r => r.json())
      .then(setDocFiles)
      .catch(() => {})
  }

  useEffect(() => { fetchDocFiles() }, [])

  const setPath = (key: string, val: string) => setPaths(p => ({ ...p, [key]: val }))

  const registerPath = async (category: string, label: string) => {
    const filePath = paths[category]?.trim()
    if (!filePath) return
    setLoading(category)
    setMessage(null)
    try {
      const r = await fetch('/api/ingest/register-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, file_path: filePath }),
      })
      if (!r.ok) {
        const err = await r.json()
        setMessage({ type: 'error', text: err.detail || `Failed to register file.` })
      } else {
        setMessage({ type: 'success', text: `Registered and indexed: ${filePath.split(/[\\/]/).pop()}` })
        setPaths(p => ({ ...p, [category]: '' }))
        fetchDocFiles()
        onRefresh()
      }
    } catch {
      setMessage({ type: 'error', text: `Could not reach the backend.` })
    } finally {
      setLoading(null)
    }
  }

  const reindex = async (endpoint: string, label: string) => {
    setLoading(label)
    setMessage(null)
    try {
      await fetch(endpoint, { method: 'POST' })
      setMessage({ type: 'success', text: `${label} re-indexed successfully.` })
      onRefresh()
    } catch {
      setMessage({ type: 'error', text: `Re-index failed for ${label}.` })
    } finally {
      setLoading(null)
    }
  }

  const handlePullModel = async () => {
    if (!pullModel.trim()) return
    setLoading('pull')
    try {
      const r = await fetch('/api/setup/pull-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: pullModel.trim() }),
      })
      const d = await r.json()
      if (d.ok) setMessage({ type: 'success', text: `Model "${pullModel}" pulled successfully.` })
      else setMessage({ type: 'error', text: d.detail || 'Pull failed.' })
      onRefresh()
    } catch {
      setMessage({ type: 'error', text: 'Model pull failed.' })
    } finally {
      setLoading(null)
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 20 }}>Document Library</h1>

      {message && (
        <div className={`alert alert-${message.type === 'success' ? 'success' : 'error'}`} style={{ marginBottom: 16 }}>
          {message.text}
        </div>
      )}

      {/* Collection status */}
      <div className="card">
        <h2>Vector Store Collections</h2>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {status ? Object.entries(status.collection_counts).map(([name, count]) => (
            <div key={name} style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 20px', minWidth: 140 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>{name}</div>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{count}</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>chunks</div>
            </div>
          )) : <span style={{ color: '#6b7280' }}>Loading…</span>}
        </div>
      </div>

      {/* Document categories */}
      {CATEGORIES.map(cat => {
        const registeredFiles: string[] = docFiles ? (docFiles as any)[cat.key] ?? [] : []
        return (
          <div className="card" key={cat.key}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 8 }}>
              <div style={{ flex: 1 }}>
                <h2 style={{ margin: '0 0 4px' }}>{cat.label}</h2>
                <div style={{ fontSize: 13, color: '#6b7280' }}>{cat.description}</div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>Accepted: {cat.accepted}</div>
              </div>
              {cat.reindexEndpoint && registeredFiles.length > 0 && (
                <button
                  className="btn btn-secondary"
                  style={{ flexShrink: 0 }}
                  onClick={() => reindex(cat.reindexEndpoint!, cat.label)}
                  disabled={loading === cat.label}
                >
                  {loading === cat.label ? <span className="spinner" /> : '🔄'} Re-index
                </button>
              )}
            </div>

            {/* Registered files */}
            {registeredFiles.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>Registered files:</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {registeredFiles.map(f => (
                    <span key={f} style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 4, padding: '2px 8px', fontSize: 12 }}>
                      ✓ {f}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Path input */}
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                style={{ flex: 1, fontFamily: 'monospace', fontSize: 13 }}
                placeholder={`Paste full file path, e.g. C:\\Users\\...\\file.xlsx`}
                value={paths[cat.key] ?? ''}
                onChange={e => setPath(cat.key, e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') registerPath(cat.key, cat.label) }}
              />
              <button
                className="btn btn-primary"
                onClick={() => registerPath(cat.key, cat.label)}
                disabled={loading === cat.key || !paths[cat.key]?.trim()}
              >
                {loading === cat.key ? <span className="spinner" /> : 'Register'}
              </button>
            </div>
          </div>
        )
      })}

      {/* Ollama model management */}
      <div className="card">
        <h2>Ollama Models</h2>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>Locally available models:</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {status?.local_models?.length
              ? status.local_models.map(m => <span key={m} className="badge badge-gray">{m}</span>)
              : <span style={{ fontSize: 13, color: '#6b7280' }}>None detected</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <input
            style={{ flex: 1 }}
            placeholder={`Recommended: ${status?.recommended_model || 'qwen2.5:14b'}`}
            value={pullModel}
            onChange={e => setPullModel(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={handlePullModel}
            disabled={loading === 'pull' || !pullModel.trim()}
          >
            {loading === 'pull' ? <span className="spinner" /> : null} Pull Model
          </button>
        </div>
        <div style={{ fontSize: 13, color: '#6b7280', marginTop: 8 }}>
          Embedding model also required: <code>nomic-embed-text</code>
        </div>
      </div>
    </div>
  )
}
