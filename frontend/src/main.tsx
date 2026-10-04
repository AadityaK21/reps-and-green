import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './theme.css'

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 15_000 } } })
document.documentElement.setAttribute('data-theme', localStorage.getItem('rng_theme') || 'light')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
