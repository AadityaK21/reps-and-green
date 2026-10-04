import { useEffect, useRef, useState } from 'react'
import { api, wsUrl } from '../api'
import { useStore } from '../store'

type Msg = { from: string; text: string; ts: number }

export default function Chat() {
  const { user } = useStore()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const wsRef = useRef<WebSocket | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get<Msg[]>('/chat/history').then(setMsgs).catch(() => {})
    const ws = new WebSocket(wsUrl())
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data)
      setMsgs((prev) => [...prev, m])
    }
    wsRef.current = ws
    return () => ws.close()
  }, [])

  useEffect(() => { bodyRef.current?.scrollTo(0, 1e9) }, [msgs])

  function send() {
    const t = text.trim()
    if (!t) return
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ text: t }))
    } else {
      api.post('/chat/send', { text: t }).then(() => setMsgs((p) => [...p, { from: 'client', text: t, ts: Date.now() / 1000 }]))
    }
    setText('')
  }

  return (
    <div className="flex h-[calc(100vh-160px)] flex-col pt-2">
      <div className="mb-2 flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-ink font-bold text-brand">S</span>
        <div><p className="text-sm font-bold">Sanya Narang</p><p className="text-[11px] font-semibold text-brand">Live chat</p></div>
      </div>
      <div ref={bodyRef} className="flex-1 space-y-2 overflow-y-auto py-2">
        {msgs.length === 0 && <p className="pt-8 text-center text-xs font-semibold text-inksoft">Say hi — Sanya replies here in real time.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 text-sm font-medium ${m.from === 'client' ? 'ml-auto rounded-br-md bg-ink text-canvas' : 'rounded-bl-md border border-line bg-card'}`}>
            {m.text}
          </div>
        ))}
      </div>
      <div className="flex gap-2 py-2">
        <input className="field flex-1 rounded-full" placeholder="Message Sanya…" value={text}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} />
        <button onClick={send} className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-ink font-bold text-canvas">→</button>
      </div>
    </div>
  )
}
