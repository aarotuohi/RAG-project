import { useState, FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | null>(null)
  const [loading, setLoading]   = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? 'Login failed')
        return
      }
      const data = await res.json()
      login(data.access_token, data.username, data.is_admin)
    } catch {
      setError('Network error — please try again')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f3f4f6',
        gap: 24,
      }}
    >
      <img
        src="/LINK_LOGO.png"
        alt="AISALES"
        style={{ height: 52, objectFit: 'contain' }}
      />
      <div
        style={{
          background: '#fff',
          borderRadius: 12,
          padding: '40px 48px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.10)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'stretch',
          gap: 16,
          minWidth: 320,
          width: 360,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#111827', textAlign: 'center' }}>
          Sign in to AISALES
        </h2>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 13, fontWeight: 500, color: '#374151' }}>Username</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              style={{
                padding: '8px 12px',
                borderRadius: 6,
                border: '1px solid #d1d5db',
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 13, fontWeight: 500, color: '#374151' }}>Password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              style={{
                padding: '8px 12px',
                borderRadius: 6,
                border: '1px solid #d1d5db',
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>

          {error && (
            <p style={{ margin: 0, color: '#dc2626', fontSize: 13, textAlign: 'center' }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: 4,
              padding: '10px 0',
              borderRadius: 8,
              border: 'none',
              background: loading ? '#9ca3af' : '#2563eb',
              color: '#fff',
              fontSize: 15,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

