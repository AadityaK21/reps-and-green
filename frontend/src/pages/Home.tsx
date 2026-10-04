import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useStore } from '../store'

const today = () => new Date().toISOString().slice(0, 10)

export default function Home() {
  const { user } = useStore()
  const nav = useNavigate()
  const goal = user?.daily_kcal || 1500
  const plan = useQuery({ queryKey: ['plan'], queryFn: () => api.get<any>('/fitness/plan') })
  const exlog = useQuery({ queryKey: ['exlog', today()], queryFn: () => api.get<any[]>(`/fitness/exercise-log/${today()}`) })
  const mlog = useQuery({ queryKey: ['mlog', today()], queryFn: () => api.get<any[]>(`/fitness/meal-log/${today()}`) })
  const water = useQuery({ queryKey: ['water', today()], queryFn: () => api.get<any>(`/fitness/water/${today()}`) })

  const total = plan.data?.exercises?.length || 5
  const done = exlog.data?.filter((e) => e.done).length || 0
  const kcal = (mlog.data || []).reduce((s, m) => s + m.kcal, 0)
  const glasses = water.data?.glasses || 0
  const score = Math.round(((done / total + Math.min(1, kcal / goal) + Math.min(1, glasses / 8)) / 3) * 100)

  return (
    <div className="space-y-4 pt-2">
      <div className="grid grid-cols-2 gap-3">
        <button onClick={() => nav('/train')} className="card p-4 text-left">
          <p className="text-[10px] font-bold uppercase tracking-wide text-inksoft">Workout</p>
          <p className="mt-2 font-num text-2xl font-bold">{done}/{total}</p>
          <p className="text-xs text-inksoft">exercises</p>
        </button>
        <button onClick={() => nav('/eat')} className="card p-4 text-left">
          <p className="text-[10px] font-bold uppercase tracking-wide text-inksoft">Calories</p>
          <p className="mt-2 font-num text-2xl font-bold">{kcal}</p>
          <p className="text-xs text-inksoft">/{goal} kcal</p>
        </button>
      </div>
      <div className="rounded-3xl bg-ink p-5 text-canvas">
        <p className="text-[10px] font-bold uppercase tracking-widest opacity-60">Day score</p>
        <div className="mt-1 flex items-end justify-between">
          <p className="font-disp text-5xl font-extrabold">{score}<span className="text-base opacity-50">/100</span></p>
          <span className="grid h-16 w-16 place-items-center rounded-full" style={{ background: `conic-gradient(var(--green) ${score}%, rgba(255,255,255,.14) 0)` }}>
            <span className="grid h-12 w-12 place-items-center rounded-full bg-ink font-num font-bold">{score}</span>
          </span>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-[11px] font-semibold opacity-90">
          {[['Move', done / total, 'var(--coral)'], ['Fuel', Math.min(1, kcal / goal), 'var(--green)'], ['Water', Math.min(1, glasses / 8), 'var(--blue)']].map(([l, f, c]) => (
            <div key={l as string}>
              <p>{l as string}</p>
              <div className="mt-1 h-1.5 rounded bg-white/15"><i className="block h-full rounded" style={{ width: `${(f as number) * 100}%`, background: c as string }} /></div>
            </div>
          ))}
        </div>
      </div>
      <button onClick={() => nav('/chat')} className="card flex w-full items-center gap-3 p-4 text-left">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-ink font-bold text-brand">S</span>
        <span className="flex-1 text-sm font-semibold text-inksoft">Ask Sanya anything…</span>
      </button>
    </div>
  )
}
