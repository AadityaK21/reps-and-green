import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useStore } from '../store'

const today = () => new Date().toISOString().slice(0, 10)
const SUGGESTED = [
  { slot: 'breakfast', name: 'Veggie oats + 2 eggs', kcal: 320, protein_g: 24, carbs_g: 34, fat_g: 9 },
  { slot: 'lunch', name: 'Dal · brown rice · salad', kcal: 480, protein_g: 22, carbs_g: 62, fat_g: 11 },
  { slot: 'snack', name: 'Whey shake + banana', kcal: 160, protein_g: 25, carbs_g: 18, fat_g: 2 },
  { slot: 'dinner', name: 'Grilled paneer + greens', kcal: 420, protein_g: 30, carbs_g: 14, fat_g: 24 },
]

export default function Eat() {
  const qc = useQueryClient()
  const { user, showToast } = useStore()
  const goal = user?.daily_kcal || 1500
  const logs = useQuery({ queryKey: ['mlog', today()], queryFn: () => api.get<any[]>(`/fitness/meal-log/${today()}`) })
  const water = useQuery({ queryKey: ['water', today()], queryFn: () => api.get<any>(`/fitness/water/${today()}`) })
  const kcal = (logs.data || []).reduce((s, m) => s + m.kcal, 0)
  const glasses = water.data?.glasses ?? 0

  const logMeal = useMutation({
    mutationFn: (m: any) => api.post('/fitness/meal-log', { date: today(), ...m }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mlog', today()] }); showToast('Meal logged') },
  })
  const setWater = useMutation({
    mutationFn: (g: number) => api.post('/fitness/water', { date: today(), glasses: g }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['water', today()] }),
  })

  const loggedNames = new Set((logs.data || []).map((m) => m.name))

  return (
    <div className="pt-2">
      <p className="text-[11px] font-bold uppercase tracking-wide text-inksoft">Nutrition</p>
      <h1 className="mb-4 font-disp text-2xl font-extrabold">Fuel the work</h1>
      <div className="card flex items-center justify-between p-5">
        <div>
          <p className="font-num text-3xl font-bold">{Math.max(0, goal - kcal)}</p>
          <p className="text-xs text-inksoft">kcal left of {goal}</p>
        </div>
        <span className="grid h-20 w-20 place-items-center rounded-full" style={{ background: `conic-gradient(var(--green) ${Math.min(100, (kcal / goal) * 100)}%, var(--tint) 0)` }}>
          <span className="grid h-14 w-14 place-items-center rounded-full bg-card font-num text-sm font-bold">{kcal}</span>
        </span>
      </div>
      <h2 className="seglabel">Today's plan</h2>
      <div className="space-y-2.5">
        {SUGGESTED.map((m) => {
          const done = loggedNames.has(m.name)
          return (
            <div key={m.slot} className={`card flex items-center gap-3 p-4 ${done ? 'opacity-60' : ''}`}>
              <div className="flex-1">
                <p className="text-[10px] font-bold uppercase text-inksoft">{m.slot}</p>
                <p className="text-sm font-bold">{m.name}</p>
              </div>
              <div className="text-right">
                <p className="font-num text-sm font-bold">{m.kcal} kcal</p>
                <button disabled={done} onClick={() => logMeal.mutate(m)} className={`mt-1 rounded-lg px-3 py-1.5 text-xs font-bold ${done ? 'bg-[var(--green-soft)] text-brand' : 'bg-ink text-canvas'}`}>
                  {done ? '✓ Logged' : 'Log'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
      <h2 className="seglabel">Water</h2>
      <div className="card flex items-center justify-between p-4">
        <div className="flex gap-1.5">
          {Array.from({ length: 8 }, (_, i) => (
            <button key={i} onClick={() => setWater.mutate(i + 1 === glasses ? i : i + 1)}
              className={`h-8 w-6 rounded-b-lg rounded-t border-2 border-blue ${i < glasses ? 'bg-blue' : 'opacity-40'}`} />
          ))}
        </div>
        <button onClick={() => setWater.mutate(Math.min(8, glasses + 1))} className="grid h-10 w-10 place-items-center rounded-xl bg-blue text-xl font-bold text-white">+</button>
      </div>
    </div>
  )
}
