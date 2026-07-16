import { useMsal } from '@azure/msal-react'
import { LOGIN_REQUEST } from '../authConfig'

export default function LoginPage() {
  const { instance } = useMsal()

  const handleLogin = () => {
    instance
      .loginPopup(LOGIN_REQUEST)
      .catch(err => {
        // Popup closed by user — not a real error
        if (err?.errorCode !== 'user_cancelled') {
          console.error('[MSAL] Login failed:', err)
        }
      })
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
          alignItems: 'center',
          gap: 20,
          minWidth: 320,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#111827' }}>
          Sign in to AISALES
        </h2>
        <p style={{ margin: 0, color: '#6b7280', fontSize: 14, textAlign: 'center' }}>
          Use your Microsoft or Outlook account to continue.
        </p>
        <button
          onClick={handleLogin}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 24px',
            borderRadius: 8,
            border: '1px solid #d1d5db',
            background: '#fff',
            cursor: 'pointer',
            fontSize: 15,
            fontWeight: 600,
            color: '#111827',
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          }}
        >
          <MicrosoftIcon />
          Sign in with Microsoft
        </button>
      </div>
    </div>
  )
}

function MicrosoftIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
      <rect x="1"  y="1"  width="9" height="9" fill="#F25022" />
      <rect x="11" y="1"  width="9" height="9" fill="#7FBA00" />
      <rect x="1"  y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </svg>
  )
}
