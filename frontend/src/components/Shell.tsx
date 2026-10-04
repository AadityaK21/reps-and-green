import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useStore } from '../store'

const tabs = [
  { to: '/', label: 'Home' },
  { to: '/train', label: 'Train' },
  { to: '/chat', label: 'Coach', center: true },
  { to: '/eat', label: 'Eat' },
  { to: '/shop', label: 'Shop' },
]

export default function Shell() {
  const { user } = useStore()
  const nav = useNavigate()
  return (
    <div className="flex min-h-screen flex-col pb-24">
      <header className="sticky top-0 z-30 flex items-center justify-between bg-canvas px-4 py-3">
        <button onClick={() => nav('/profile')} className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-ink font-disp text-base font-extrabold text-brand">
            {(user?.name || 'A')[0].toUpperCase()}
          </span>
          <span className="text-left">
            <span className="block font-disp text-lg font-extrabold leading-none">Hi, {user?.name || 'there'}</span>
            <span className="block text-xs text-inksoft">Reps &amp; Greens</span>
          </span>
        </button>
        {user?.role === 'coach' && (
          <button onClick={() => nav('/coach')} className="rounded-xl border border-line bg-card px-3 py-2 text-xs font-bold">
            Coach view
          </button>
        )}
      </header>
      <main className="flex-1 px-4"><Outlet /></main>
      <nav className="fixed bottom-0 left-1/2 z-40 flex w-full max-w-[430px] -translate-x-1/2 items-center justify-around border-t border-line bg-canvas/90 px-2 pb-4 pt-2 backdrop-blur">
        {tabs.map((t) =>
          t.center ? (
            <NavLink key={t.to} to={t.to} className="flex flex-col items-center text-[10px] font-semibold text-inksoft">
              {({ isActive }) => (
                <>
                  <span className={`grid h-12 w-12 -mt-5 place-items-center rounded-full shadow-lg ${isActive ? 'bg-brand text-white' : 'bg-ink text-brand'}`}>S</span>
                  <span className="mt-0.5">{t.label}</span>
                </>
              )}
            </NavLink>
          ) : (
            <NavLink key={t.to} to={t.to} className={({ isActive }) => `flex flex-col items-center gap-0.5 px-3 py-1 text-[11px] font-semibold ${isActive ? 'text-ink' : 'text-inksoft'}`}>
              {t.label}
            </NavLink>
          ),
        )}
      </nav>
    </div>
  )
}
