/**
 * Authenticated fetch wrapper.
 *
 * Before each /api/ request the wrapper reads the JWT from sessionStorage
 * and attaches it as a Bearer header.  When no token is present (auth not
 * configured or user not logged in) the request is sent without a header.
 *
 * Usage — import in any component instead of the global fetch:
 *   import { apiFetch } from '../auth/apiFetch'
 *   const r = await apiFetch('/api/status')
 */

const _TOKEN_KEY = 'aisales_token'

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)

  const token = sessionStorage.getItem(_TOKEN_KEY)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  return fetch(url, { ...init, headers })
}
