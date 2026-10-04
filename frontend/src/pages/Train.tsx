import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useStore } from '../store'

const today = () => new Date().toISOString().slice(0, 10)

export default function Train() {
  const qc = useQueryClient()
  const { showToast } = useStore()
  const plan = useQuery({ queryKey: ['plan'], queryFn: () => api.get<any>('/fitness/plan') })
  const log = useQuery({ queryKey: ['exlog', today()], queryFn: () => api.get<any[]>(`/fitness/exercise-log/${today()}`) })
  const doneSet = new Set((log.data || []).filter((e) => e.done).map((e) => e.exercise))

  const toggle = useMutation({
    mutationFn: (ex: string) => api.post('/fitness/exercise-log', { date: today(), exercise: ex, done: !doneSet.has(ex) }),
    onSuccess: (_d, ex) => {
      qc.invalidateQueries({ queryKey: ['exlog', today()] })
      const willDone = !doneSet.has(ex)
      const totalDone = doneSet.size + (willDone ? 1 : -1)
      if (willDone && totalDone === (plan.data?.exercises?.length || 5)) showToast('Workout complete — great work!')
    },
  })

  return (
    <div className="pt-2">
      <p className="text-[11px] font-bold uppercase tracking-wide text-inksoft">Train</p>
      <h1 className="mb-4 font-disp text-2xl font-extrabold">{plan.data?.title || 'Today’s workout'}</h1>
      <div className="space-y-2.5">
        {(plan.data?.exercises || []).map((e: any) => {
          const d = doneSet.has(e.name)
          return (
            <button key={e.name} onClick={() => toggle.mutate(e.name)}
              className={`flex w-full items-center gap-3 rounded-2xl border p-4 text-left ${d ? 'border-brand bg-[var(--green-soft)]' : 'border-line bg-card'}`}>
              <span className={`grid h-7 w-7 place-items-center rounded-full border-2 text-xs font-bold ${d ? 'border-brand bg-brand text-white' : 'border-line'}`}>{d ? '✓' : ''}</span>
              <span className="flex-1">
                <span className={`block text-[15px] font-bold ${d ? 'text-inksoft line-through' : ''}`}>{e.name}</span>
                <span className="block text-xs text-inksoft">{e.detail}</span>
              </span>
              <span className="text-xs font-bold text-brand">{d ? 'Done' : 'Start'}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
