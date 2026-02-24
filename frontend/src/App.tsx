import { useState, useEffect } from 'react'
import DocumentsTab from './tabs/DocumentsTab'
import NewOfferTab from './tabs/NewOfferTab'
import OutputsTab from './tabs/OutputsTab'

type Tab = 'documents' | 'new-offer' | 'outputs'

interface Status {
  ollama_running: boolean
  recommended_model: string
  local_models: string[]
  collection_counts: Record<string, number>
}

export default function App() {
  const [tab, setTab] = useState<Tab>('new-offer')
  const [status, setStatus] = useState<Status | null>(null)

  const fetchStatus = () => {
    fetch('/api/status')
      .then(r => r.json())
      .then(setStatus)
      .catch(() => setStatus(null))
  }

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 10_000)
    return () => clearInterval(interval)
  }, [])

  const ollamaOk = status?.ollama_running ?? false

  return (
    <div className="app">
      <nav className="nav">
        <span className="nav-brand">AISALES</span>
        {(['documents', 'new-offer', 'outputs'] as Tab[]).map(t => (
          <button
            key={t}
            className={`nav-tab${tab === t ? ' active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'documents' ? '📁 Documents' : t === 'new-offer' ? '✍️ New Offer' : '📄 Outputs'}
          </button>
        ))}
        <div className="nav-status">
          <span className={`dot${ollamaOk ? ' ok' : ''}`} />
          <span>Ollama {ollamaOk ? 'running' : 'offline'}</span>
          {status?.recommended_model && (
            <span className="badge badge-blue" style={{ marginLeft: 8 }}>
              {status.recommended_model}
            </span>
          )}
        </div>
      </nav>
      <main className="content">
        {tab === 'documents' && <DocumentsTab status={status} onRefresh={fetchStatus} />}
        {tab === 'new-offer' && <NewOfferTab />}
        {tab === 'outputs' && <OutputsTab />}
      </main>
    </div>
  )
}
