import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, clearToken } from '../api'
import { useStore } from '../store'

export default function Profile() {
  const { user, setUser, theme, toggleTheme, showToast } = useStore()
  const nav = useNavigate()
  const orders = useQuery({ queryKey: ['orders'], queryFn: () => api.get<any[]>('/shop/orders') })
  const weights = useQuery({ queryKey: ['weights'], queryFn: () => api.get<any[]>('/fitness/weight') })

  async function logWeight() {
    const v = prompt('Current weight (kg)?')
    if (!v) return
    await api.post('/fitness/weight', { date: new Date().toISOString().slice(0, 10), weight_kg: parseFloat(v) })
    weights.refetch(); showToast('Weight logged')
  }

  return (
    <div className="px-4 pb-10 pt-4">
      <button onClick={() => nav(-1)} className="mb-4 grid h-10 w-10 place-items-center rounded-xl border border-line bg-card">←</button>
      <div className="text-center">
        <span className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-ink font-disp text-3xl font-extrabold text-brand">{(user?.name || 'A')[0].toUpperCase()}</span>
        <h1 className="mt-3 font-disp text-xl font-extrabold">{user?.name}</h1>
        <p className="text-sm text-inksoft">{user?.email}</p>
      </div>
      <h2 className="seglabel">Progress</h2>
      <div className="card p-4">
        <div className="flex items-center justify-between">
          <p className="font-num text-xl font-bold">{weights.data?.at(-1)?.weight_kg ?? '—'} kg</p>
          <button onClick={logWeight} className="rounded-xl bg-ink px-3 py-2 text-xs font-bold text-canvas">Log weight</button>
        </div>
        <p className="mt-1 text-xs text-inksoft">{weights.data?.length || 0} entries</p>
      </div>
      <h2 className="seglabel">Order history</h2>
      <div className="card divide-y divide-line">
        {(orders.data || []).length === 0 && <p className="p-4 text-center text-xs font-semibold text-inksoft">No orders yet</p>}
        {(orders.data || []).map((o) => (
          <div key={o.id} className="flex items-center justify-between p-4">
            <div><p className="text-sm font-bold">₹{o.total.toLocaleString('en-IN')}</p><p className="text-xs text-inksoft">{o.items.map((i: any) => i.name).join(', ').slice(0, 40)}</p></div>
            <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${o.status === 'paid' ? 'bg-[var(--green-soft)] text-brand' : 'bg-tint text-inksoft'}`}>{o.status}</span>
          </div>
        ))}
      </div>
      <h2 className="seglabel">Preferences</h2>
      <div className="card flex items-center justify-between p-4">
        <p className="text-sm font-bold">Dark mode</p>
        <button onClick={toggleTheme} className={`h-7 w-12 rounded-full p-0.5 transition ${theme === 'dark' ? 'bg-brand' : 'bg-line'}`}>
          <span className={`block h-6 w-6 rounded-full bg-white transition ${theme === 'dark' ? 'translate-x-5' : ''}`} />
        </button>
      </div>
      <button className="btn btn-ghost mt-6" onClick={() => { clearToken(); setUser(null); nav('/auth') }}>
        <span className="text-[#E5484D]">Log out</span>
      </button>
    </div>
  )
}
