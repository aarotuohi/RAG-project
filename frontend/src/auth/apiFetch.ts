/**
 * Authenticated fetch wrapper.
 *
 * Before each /api/ request the wrapper silently acquires a fresh access
 * token from MSAL (using the refresh token when the cached one is expired)
 * and attaches it as a Bearer header.
 *
 * Usage — import in any component instead of the global fetch:
 *   import { apiFetch } from '../auth/apiFetch'
 *   const r = await apiFetch('/api/status')
 *
 * Token getter is registered once from App.tsx after MSAL initialises.
 * When no getter is registered (auth not configured) requests are sent
 * without an Authorization header so local dev still works.
 */

type TokenGetter = () => Promise<string | null>

let _getToken: TokenGetter | null = null

/** Called once from App.tsx after MSAL is ready. */
export function setTokenGetter(fn: TokenGetter): void {
  _getToken = fn
}

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)

  if (_getToken) {
    try {
      const token = await _getToken()
      if (token) headers.set('Authorization', `Bearer ${token}`)
    } catch {
      // Silent acquisition failed (e.g. consent required, session expired).
      // Send the request without a token — the backend returns 401 and the
      // AuthenticatedApp component will prompt the user to log in again.
    }
  }

  return fetch(url, { ...init, headers })
}
