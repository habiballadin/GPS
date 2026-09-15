'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

type Credentials = { email: string; password: string }
type Registration = Credentials & { organization_name: string }
type AuthContextValue = { token: string | null; ready: boolean; login: (input: Credentials) => Promise<void>; register: (input: Registration) => Promise<void>; logout: () => void }
const AuthContext = createContext<AuthContextValue | null>(null)

type TokenResponse = { access_token: string; refresh_token?: string; expires_in?: number }
async function requestToken(path: string, body: Credentials | Registration) {
  const response = await fetch(`/api/v1/auth/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? 'Authentication failed')
  return await response.json() as TokenResponse
}

function tokenExpiresAt(token: string | null): number | null {
  if (!token) return null
  try {
    const payload = JSON.parse(window.atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch { return null }
}

async function refreshAccessToken(): Promise<TokenResponse | null> {
  const refresh = window.localStorage.getItem('fleet_refresh_token')
  if (!refresh) return null
  const response = await fetch('/api/v1/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }) })
  if (!response.ok) return null
  return await response.json() as TokenResponse
}

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [token, setToken] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const router = useRouter()
  useEffect(() => {
    let timer: number | undefined
    const clearSession = () => { window.localStorage.removeItem('fleet_token'); window.localStorage.removeItem('fleet_refresh_token'); setToken(null) }
    const applyRefresh = (next: TokenResponse) => { window.localStorage.setItem('fleet_token', next.access_token); if (next.refresh_token) window.localStorage.setItem('fleet_refresh_token', next.refresh_token); setToken(next.access_token) }
    const initialize = async () => {
      const access = window.localStorage.getItem('fleet_token')
      const expiresAt = tokenExpiresAt(access)
      if (access && expiresAt && expiresAt > Date.now() + 60_000) setToken(access)
      else {
        const next = await refreshAccessToken()
        if (next) applyRefresh(next); else if (access) clearSession()
      }
      setReady(true)
      if (!window.localStorage.getItem('fleet_refresh_token')) return
      timer = window.setInterval(async () => { const next = await refreshAccessToken(); if (next) applyRefresh(next); else clearSession() }, 15 * 60 * 1000)
    }
    void initialize()
    return () => { if (timer) window.clearInterval(timer) }
  }, [])
  const value = useMemo<AuthContextValue>(() => ({
    token, ready,
    async login(input) { const next = await requestToken('login', input); window.localStorage.setItem('fleet_token', next.access_token); if (next.refresh_token) window.localStorage.setItem('fleet_refresh_token', next.refresh_token); setToken(next.access_token); router.push('/dashboard') },
    async register(input) { const next = await requestToken('register', input); window.localStorage.setItem('fleet_token', next.access_token); if (next.refresh_token) window.localStorage.setItem('fleet_refresh_token', next.refresh_token); setToken(next.access_token); router.push('/dashboard') },
    logout() { window.localStorage.removeItem('fleet_token'); window.localStorage.removeItem('fleet_refresh_token'); setToken(null); router.push('/login') },
  }), [ready, router, token])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
