import { useState, useEffect } from 'react'

interface OutputFile {
  name: string
  path: string
  size: number
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function OutputsTab() {
  const [files, setFiles] = useState<OutputFile[]>([])
  const [loading, setLoading] = useState(true)

  const fetchOutputs = () => {
    setLoading(true)
    fetch('/api/outputs')
      .then(r => r.json())
      .then(setFiles)
      .catch(() => setFiles([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchOutputs() }, [])

  const download = (path: string) => {
    window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
  }

  const docxFiles = files.filter(f => f.name.endsWith('.docx'))
  const pdfFiles  = files.filter(f => f.name.endsWith('.pdf'))

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Generated Offers</h1>
        <button className="btn btn-secondary" onClick={fetchOutputs}>🔄 Refresh</button>
      </div>

      {loading && <div style={{ color: '#6b7280', fontSize: 14 }}>Loading…</div>}

      {!loading && files.length === 0 && (
        <div className="alert alert-info">
          No offers generated yet. Go to the <strong>New Offer</strong> tab to create one.
        </div>
      )}

      {docxFiles.length > 0 && (
        <div className="card">
          <h2>Word Documents (.docx)</h2>
          {docxFiles.map(f => (
            <div key={f.path} className="output-item">
              <span className="output-icon">📝</span>
              <span className="output-name">{f.name}</span>
              <span className="output-size">{formatSize(f.size)}</span>
              <button className="btn btn-secondary" style={{ padding: '6px 14px' }} onClick={() => download(f.path)}>
                ⬇️ Download
              </button>
            </div>
          ))}
        </div>
      )}

      {pdfFiles.length > 0 && (
        <div className="card">
          <h2>PDF Documents</h2>
          {pdfFiles.map(f => (
            <div key={f.path} className="output-item">
              <span className="output-icon">📄</span>
              <span className="output-name">{f.name}</span>
              <span className="output-size">{formatSize(f.size)}</span>
              <button className="btn btn-primary" style={{ padding: '6px 14px' }} onClick={() => download(f.path)}>
                ⬇️ Download
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
