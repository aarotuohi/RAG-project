/**
 * Auth configuration.
 *
 * AUTH_CONFIGURED is true when the backend is set up with a JWT_SECRET
 * (i.e. VITE_AUTH_ENABLED=true in frontend/.env).  When false the app
 * runs without a login screen — useful for local development.
 */

export const AUTH_CONFIGURED = import.meta.env.VITE_AUTH_ENABLED === 'true'

