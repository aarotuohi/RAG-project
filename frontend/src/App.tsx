import { useState, useEffect } from 'react'
import NewOfferTab from './tabs/NewOfferTab'
import OutputsTab from './tabs/OutputsTab'
import { t, type Lang } from './i18n'

type Tab = 'new-offer' | 'outputs'

interface Status {
  ollama_running: boolean
  recommended_model: string
  local_models: string[]
  collection_counts: Record<string, number>
}

export default function App() {
  const [tab, setTab] = useState<Tab>('new-offer')
  const [status, setStatus] = useState<Status | null>(null)
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('aisales_lang') as Lang) || 'en')

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

  const toggleLang = () => {
    const next: Lang = lang === 'en' ? 'fi' : 'en'
    setLang(next)
    localStorage.setItem('aisales_lang', next)
  }

  const ollamaOk = status?.ollama_running ?? false

  const tabLabels: Record<Tab, string> = {
    'new-offer': t('nav_new_offer', lang),
    'outputs':   t('nav_outputs', lang),
  }

  return (
    <div className="app">
      <nav className="nav">
        <span className="nav-brand">AISALES</span>
        {(['new-offer', 'outputs'] as Tab[]).map(tab_ => (
          <button
            key={tab_}
            className={`nav-tab${tab === tab_ ? ' active' : ''}`}
            onClick={() => setTab(tab_)}
          >
            {tabLabels[tab_]}
          </button>
        ))}
        <div className="nav-status">
          <span className={`dot${ollamaOk ? ' ok' : ''}`} />
          <span>{ollamaOk ? t('ollama_running', lang) : t('ollama_offline', lang)}</span>
          {status?.recommended_model && (
            <span className="badge badge-blue" style={{ marginLeft: 8 }}>
              {status.recommended_model}
            </span>
          )}
          <button
            onClick={toggleLang}
            style={{
              marginLeft: 12,
              padding: '4px 10px',
              borderRadius: 6,
              border: '1px solid #d1d5db',
              background: '#f9fafb',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
            }}
            title={lang === 'en' ? 'Switch to Finnish' : 'Vaihda englanniksi'}
          >
            {lang === 'en' ? '🇫🇮 FI' : '🇬🇧 EN'}
          </button>
        </div>
      </nav>
      <main className="content">
        {tab === 'new-offer' && <NewOfferTab lang={lang} />}
        {tab === 'outputs' && <OutputsTab lang={lang} />}
      </main>
    </div>
  )
}
