import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { useStore } from '../store'

export default function Auth() {
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const { setUser, showToast } = useStore()
  const nav = useNavigate()

  async function submit() {
    setBusy(true)
    try {
      const path = mode === 'up' ? '/auth/register' : '/auth/login'
      const body = mode === 'up' ? { name, email, password: pw } : { email, password: pw }
      const r = await api.post<any>(path, body)
      setToken(r.token); setUser(r.user)
      nav(mode === 'up' ? '/quiz' : r.user.role === 'coach' ? '/coach' : '/')
    } catch (e: any) { showToast(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="px-6 pt-14">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-ink text-2xl font-extrabold text-brand">R</div>
      <h1 className="mt-5 font-disp text-3xl font-extrabold tracking-tight">
        {mode === 'up' ? 'Create your account' : 'Welcome back'}
      </h1>
      <p className="mt-2 text-sm text-inksoft">Coaching by Sanya Narang</p>
      <div className="mt-6 flex rounded-xl bg-tint p-1">
        {(['in', 'up'] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)}
            className={`flex-1 rounded-lg py-2.5 text-sm font-bold ${mode === m ? 'bg-card shadow' : 'text-inksoft'}`}>
            {m === 'in' ? 'Log in' : 'Sign up'}
          </button>
        ))}
      </div>
      <div className="mt-5 space-y-3">
        {mode === 'up' && <input className="field" placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />}
        <input className="field" placeholder="you@email.com" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="field" placeholder="Password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <button className="btn btn-ink" disabled={busy} onClick={submit}>
          {busy ? '…' : mode === 'up' ? 'Create account' : 'Log in'}
        </button>
      </div>
      <p className="mt-5 text-center text-xs text-inksoft">Secured by JWT · passwords hashed with bcrypt</p>
    </div>
  )
}
