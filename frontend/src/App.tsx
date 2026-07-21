import { useState, useEffect } from 'react'
import { useAuth } from './auth/AuthContext'
import NewOfferTab from './tabs/NewOfferTab'
import OutputsTab from './tabs/OutputsTab'
import LoginPage from './components/LoginPage'
import { t, type Lang } from './i18n'
import { AUTH_CONFIGURED } from './authConfig'
import { apiFetch } from './auth/apiFetch'

type Tab = 'new-offer' | 'outputs'

interface ModelOption {
  id: string
  label: string
}

interface Status {
  ollama_running: boolean
  active_model: string
  recommended_model: string
  local_models: string[]
  collection_counts: Record<string, number>
  available_models: ModelOption[]
}

export default function App() {
  const [tab, setTab] = useState<Tab>('new-offer')
  const [status, setStatus] = useState<Status | null>(null)
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('aisales_lang') as Lang) || 'en')
  const [activeModel, setActiveModel] = useState<string>('')

  const { isAuthenticated, username, logout } = useAuth()

  // Only start polling once authenticated (or when auth is not configured).
  const canFetch = !AUTH_CONFIGURED || isAuthenticated

  const fetchStatus = () => {
    apiFetch('/api/status')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        if (data && typeof data === 'object' && !Array.isArray(data)) {
          setStatus(data)
          setActiveModel((prev) => prev || data.active_model || '')
        }
      })
      .catch(() => setStatus(null))
  }

  useEffect(() => {
    if (!canFetch) return
    fetchStatus()
    const interval = setInterval(fetchStatus, 10_000)
    return () => clearInterval(interval)
  }, [canFetch])

  const toggleLang = () => {
    const next: Lang = lang === 'en' ? 'fi' : 'en'
    setLang(next)
    localStorage.setItem('aisales_lang', next)
  }

  const ollamaOk = status?.ollama_running ?? false

  const handleModelChange = (modelId: string) => {
    setActiveModel(modelId)
    apiFetch('/api/set-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    }).catch(() => { /* non-critical — UI already updated */ })
  }

  const tabLabels: Record<Tab, string> = {
    'new-offer': t('nav_new_offer', lang),
    'outputs':   t('nav_outputs', lang),
  }

  // Show login page when auth is configured but the user is not signed in.
  if (AUTH_CONFIGURED && !isAuthenticated) {
    return <LoginPage />
  }

  return (
    <div className="app">
      <nav className="nav">
        <img src="/LINK_LOGO.png" alt="AISALES" className="nav-brand" style={{ height: 36, objectFit: 'contain' }} />
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
          <span style={{ minWidth: 90 }}>{ollamaOk ? t('ollama_running', lang) : t('ollama_offline', lang)}</span>
          {status?.available_models && status.available_models.length > 0 ? (
            <select
              value={activeModel}
              onChange={e => handleModelChange(e.target.value)}
              title={t('model_selector_label', lang)}
              style={{
                marginLeft: 8,
                padding: '3px 6px',
                borderRadius: 6,
                border: '1px solid #d1d5db',
                background: '#f9fafb',
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 500,
                maxWidth: 200,
              }}
            >
              {status.available_models.map(m => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          ) : (
            <span className="badge badge-blue" style={{ marginLeft: 8, minWidth: 60, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activeModel || status?.active_model || '…'}
            </span>
          )}
          <button
            onClick={toggleLang}
            style={{
              marginLeft: 12,
              padding: '3px 10px',
              borderRadius: 6,
              border: '1px solid #d1d5db',
              background: '#f9fafb',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: 1,
            }}
            title={lang === 'en' ? 'Switch to Finnish' : 'Vaihda englanniksi'}
          >
            {lang === 'en' ? 'FI' : 'EN'}
          </button>
          {AUTH_CONFIGURED && isAuthenticated && (
            <>
              <span style={{ marginLeft: 12, fontSize: 12, color: '#6b7280', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {username ?? ''}
              </span>
              <button
                onClick={logout}
                style={{
                  marginLeft: 8,
                  padding: '3px 10px',
                  borderRadius: 6,
                  border: '1px solid #d1d5db',
                  background: '#f9fafb',
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: 500,
                  color: '#374151',
                }}
                title="Sign out"
              >
                Sign out
              </button>
            </>
          )}
        </div>
      </nav>
      <main className="content">
        <div className="tab-content">
          <div style={{ display: tab === 'new-offer' ? 'block' : 'none' }}>
            <NewOfferTab lang={lang} />
          </div>
          <div style={{ display: tab === 'outputs' ? 'block' : 'none' }}>
            <OutputsTab lang={lang} isActive={tab === 'outputs'} />
          </div>
        </div>
      </main>
    </div>
  )
}

