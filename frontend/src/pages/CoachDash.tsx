import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useStore } from '../store'

export default function CoachDash() {
  const nav = useNavigate()
  const { showToast } = useStore()
  const clients = useQuery({ queryKey: ['clients'], queryFn: () => api.get<any[]>('/coach/clients') })
  const revenue = useQuery({ queryKey: ['revenue'], queryFn: () => api.get<any>('/coach/revenue') })
  const [msg, setMsg] = useState('')

  async function broadcast() {
    if (!msg.trim()) return
    const r = await api.post<any>('/coach/broadcast', { text: msg })
    showToast(`Broadcast sent to ${r.sent} clients (with phone numbers)`)
    setMsg('')
  }

  return (
    <div className="px-4 pb-10 pt-4">
      <button onClick={() => nav('/')} className="mb-4 grid h-10 w-10 place-items-center rounded-xl border border-line bg-card">←</button>
      <p className="text-[11px] font-bold uppercase tracking-wide text-inksoft">Coach view</p>
      <h1 className="mb-4 font-disp text-2xl font-extrabold">Sanya Narang</h1>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-ink p-4 text-canvas"><p className="font-disp text-2xl font-extrabold">{revenue.data?.active_clients ?? '-'}</p><p className="text-xs opacity-70">Active clients</p></div>
        <div className="rounded-2xl bg-ink p-4 text-canvas"><p className="font-disp text-2xl font-extrabold">₹{(revenue.data?.week_total ?? 0).toLocaleString('en-IN')}</p><p className="text-xs opacity-70">This week (paid)</p></div>
      </div>
      <h2 className="seglabel">WhatsApp broadcast</h2>
      <div className="card p-4">
        <input className="field" placeholder="6 AM HIIT tomorrow. Bring water!" value={msg} onChange={(e) => setMsg(e.target.value)} />
        <button onClick={broadcast} className="btn btn-brand mt-3">Send to all clients</button>
      </div>
      <h2 className="seglabel">Clients</h2>
      <div className="card divide-y divide-line">
        {(clients.data || []).map((c) => (
          <div key={c.id} className="flex items-center gap-3 p-4">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-tint font-bold">{c.name[0]}</span>
            <div className="flex-1"><p className="text-sm font-bold">{c.name}</p><p className="text-xs text-inksoft">{c.goal || 'no quiz yet'} · {c.daily_kcal} kcal</p></div>
            <p className="font-num text-sm font-bold">{c.last_weight ? `${c.last_weight}kg` : '-'}</p>
          </div>
        ))}
        {(clients.data || []).length === 0 && <p className="p-4 text-center text-xs font-semibold text-inksoft">No clients yet. Share the signup link</p>}
      </div>
    </div>
  )
}
