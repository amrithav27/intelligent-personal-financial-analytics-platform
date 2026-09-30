import { create } from 'zustand'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  setTokens: (access: string, refresh: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: localStorage.getItem('phoenix_access_token'),
  refreshToken: localStorage.getItem('phoenix_refresh_token'),
  isAuthenticated: !!localStorage.getItem('phoenix_access_token'),
  setTokens: (access, refresh) => {
    localStorage.setItem('phoenix_access_token', access)
    localStorage.setItem('phoenix_refresh_token', refresh)
    set({ accessToken: access, refreshToken: refresh, isAuthenticated: true })
  },
  logout: () => {
    localStorage.removeItem('phoenix_access_token')
    localStorage.removeItem('phoenix_refresh_token')
    set({ accessToken: null, refreshToken: null, isAuthenticated: false })
  },
}))
