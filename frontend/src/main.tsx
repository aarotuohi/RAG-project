import ReactDOM from 'react-dom/client'
import { MsalProvider } from '@azure/msal-react'
import { PublicClientApplication } from '@azure/msal-browser'
import { msalConfig } from './authConfig'
import App from './App'
import './index.css'

// msalInstance is created once and passed to MsalProvider so MSAL state is
// shared across the whole application.
const msalInstance = new PublicClientApplication(msalConfig)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <MsalProvider instance={msalInstance}>
    <App />
  </MsalProvider>
)
