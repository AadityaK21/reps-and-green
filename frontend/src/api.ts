const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function token() { return localStorage.getItem('rng_token') || '' }
export function setToken(t: string) { localStorage.setItem('rng_token', t) }
export function clearToken() { localStorage.removeItem('rng_token') }

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}`, ...(opts.headers || {}) },
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(body.detail || 'Request failed')
  }
  return r.json()
}

export const api = {
  get: <T>(p: string) => req<T>(p),
  post: <T>(p: string, body?: unknown) => req<T>(p, { method: 'POST', body: JSON.stringify(body ?? {}) }),
  patch: <T>(p: string, body?: unknown) => req<T>(p, { method: 'PATCH', body: JSON.stringify(body ?? {}) }),
  del: <T>(p: string) => req<T>(p, { method: 'DELETE' }),
}

export function wsUrl() {
  const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/^http/, 'ws')
  return `${base}/chat/ws?token=${token()}`
}

export type User = { id: string; name: string; email: string; role: 'client' | 'coach'; daily_kcal: number; quiz: unknown; phone: string }
