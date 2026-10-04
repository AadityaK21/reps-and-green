import { useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { api, token } from './api'
import { useStore } from './store'
import Auth from './pages/Auth'
import Quiz from './pages/Quiz'
import Home from './pages/Home'
import Train from './pages/Train'
import Eat from './pages/Eat'
import Shop from './pages/Shop'
import Chat from './pages/Chat'
import Profile from './pages/Profile'
import CoachDash from './pages/CoachDash'
import Shell from './components/Shell'

export default function App() {
  const { user, setUser, toast } = useStore()
  const nav = useNavigate()

  useEffect(() => {
    if (!token()) { nav('/auth'); return }
    api.get<any>('/me').then(setUser).catch(() => { setUser(null); nav('/auth') })
  }, [])

  return (
    <div className="mx-auto min-h-screen max-w-[430px] bg-canvas relative">
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route path="/quiz" element={<Quiz />} />
        <Route element={<Shell />}>
          <Route path="/" element={<Home />} />
          <Route path="/train" element={<Train />} />
          <Route path="/eat" element={<Eat />} />
          <Route path="/shop" element={<Shop />} />
          <Route path="/chat" element={<Chat />} />
        </Route>
        <Route path="/profile" element={<Profile />} />
        <Route path="/coach" element={user?.role === 'coach' ? <CoachDash /> : <Navigate to="/" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-canvas shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
