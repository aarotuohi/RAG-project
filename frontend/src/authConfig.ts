import { Configuration, LogLevel } from '@azure/msal-browser'

// Set these in frontend/.env (or project root .env with VITE_ prefix).
// They are public identifiers — not secrets — and are safe to embed in the SPA.
const clientId = import.meta.env.VITE_AZURE_AD_CLIENT_ID as string
const tenantId = import.meta.env.VITE_AZURE_AD_TENANT_ID as string

if (!clientId || !tenantId) {
  console.warn(
    '[MSAL] VITE_AZURE_AD_CLIENT_ID and VITE_AZURE_AD_TENANT_ID are not set. ' +
    'Authentication is disabled — the app will run without login.',
  )
}

export const AUTH_CONFIGURED = Boolean(clientId && tenantId)

export const msalConfig: Configuration = {
  auth: {
    clientId: clientId || 'not-configured',
    authority: `https://login.microsoftonline.com/${tenantId || 'common'}`,
    redirectUri: window.location.origin,
    postLogoutRedirectUri: window.location.origin,
  },
  cache: {
    // sessionStorage: tokens cleared when the tab closes.
    // Safer than localStorage — mitigates token theft across browser sessions.
    cacheLocation: 'sessionStorage',
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return
        if (level === LogLevel.Error) console.error('[MSAL]', message)
      },
      piiLoggingEnabled: false,
    },
  },
}

// Scope your app registration exposes.
// Azure portal → App registration → Expose an API → Add scope "access_as_user"
// The backend validates tokens with audience = api://<clientId>
export const API_SCOPES = [`api://${clientId}/access_as_user`]

export const LOGIN_REQUEST = { scopes: API_SCOPES }
