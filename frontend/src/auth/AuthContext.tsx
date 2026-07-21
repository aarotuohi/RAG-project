/**
 * Simple JWT auth context — replaces MSAL.
 *
 * Tokens are stored in sessionStorage so they are automatically cleared when
 * the tab closes (mirrors the previous MSAL cacheLocation: 'sessionStorage').
 */
import { createContext, useContext, useState, ReactNode } from 'react'

interface AuthState {
  token: string | null
  username: string | null
  isAdmin: boolean
  isAuthenticated: boolean
}

interface AuthContextValue extends AuthState {
  login: (token: string, username: string, isAdmin: boolean) => void
  logout: () => void
}

const _TOKEN_KEY    = 'aisales_token'
const _USERNAME_KEY = 'aisales_username'
const _ADMIN_KEY    = 'aisales_is_admin'

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(() => {
    const token    = sessionStorage.getItem(_TOKEN_KEY)
    const username = sessionStorage.getItem(_USERNAME_KEY)
    const isAdmin  = sessionStorage.getItem(_ADMIN_KEY) === 'true'
    return { token, username, isAdmin, isAuthenticated: Boolean(token) }
  })

  function login(token: string, username: string, isAdmin: boolean) {
    sessionStorage.setItem(_TOKEN_KEY,    token)
    sessionStorage.setItem(_USERNAME_KEY, username)
    sessionStorage.setItem(_ADMIN_KEY,    String(isAdmin))
    setAuth({ token, username, isAdmin, isAuthenticated: true })
  }

  function logout() {
    sessionStorage.removeItem(_TOKEN_KEY)
    sessionStorage.removeItem(_USERNAME_KEY)
    sessionStorage.removeItem(_ADMIN_KEY)
    setAuth({ token: null, username: null, isAdmin: false, isAuthenticated: false })
  }

  return (
    <AuthContext.Provider value={{ ...auth, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
