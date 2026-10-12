import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useStore } from '../store'

const Q = [
  { key: 'goal', q: "What's your main goal?", opts: [['lose_fat', 'Lose fat'], ['build_strength', 'Build strength'], ['consistent', 'Stay consistent']] },
  { key: 'activity', q: 'How active are you now?', opts: [['beginner', 'Just starting'], ['some', 'A few times a week'], ['active', 'Very active']] },
  { key: 'days_per_week', q: 'Days you can commit?', opts: [['3', '3 days / week'], ['4-5', '4–5 days / week'], ['6', '6 days / week']] },
] as const

export default function Quiz() {
  const [i, setI] = useState(0)
  const [ans, setAns] = useState<Record<string, string>>({})
  const nav = useNavigate()
  const { showToast } = useStore()
  const cur = Q[i]

  async function pick(v: string) {
    const next = { ...ans, [cur.key]: v }
    setAns(next)
    if (i < Q.length - 1) { setI(i + 1); return }
    try {
      const r = await api.post<any>('/me/quiz', next)
      showToast(`Plan ready: ${r.daily_kcal} kcal/day`)
      nav('/')
    } catch (e: any) { showToast(e.message) }
  }

  return (
    <div className="px-6 pt-12">
      <div className="h-1.5 rounded bg-tint"><i className="block h-full rounded bg-ink transition-all" style={{ width: `${((i + 1) / Q.length) * 100}%` }} /></div>
      <h1 className="mt-8 font-disp text-2xl font-extrabold">{cur.q}</h1>
      <div className="mt-6 space-y-3">
        {cur.opts.map(([v, label]) => (
          <button key={v} onClick={() => pick(v)} className="w-full rounded-2xl border border-line bg-card p-4 text-left font-semibold active:scale-[.99]">
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
