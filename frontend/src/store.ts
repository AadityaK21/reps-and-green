import { create } from 'zustand'
import type { User } from './api'

type S = {
  user: User | null
  setUser: (u: User | null) => void
  theme: 'light' | 'dark'
  toggleTheme: () => void
  toast: string
  showToast: (m: string) => void
}

export const useStore = create<S>((set) => ({
  user: null,
  setUser: (u) => set({ user: u }),
  theme: (localStorage.getItem('rng_theme') as 'light' | 'dark') || 'light',
  toggleTheme: () =>
    set((s) => {
      const t = s.theme === 'light' ? 'dark' : 'light'
      localStorage.setItem('rng_theme', t)
      document.documentElement.setAttribute('data-theme', t)
      return { theme: t }
    }),
  toast: '',
  showToast: (m) => {
    set({ toast: m })
    setTimeout(() => set({ toast: '' }), 2400)
  },
}))
