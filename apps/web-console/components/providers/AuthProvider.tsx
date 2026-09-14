'use client'

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

type Credentials = { email: string; password: string }
type Registration = Credentials & { organization_name: string }
type AuthContextValue = { token: string | null; ready: boolean; login: (input: Credentials) => Promise<void>; register: (input: Registration) => Promise<void>; logout: () => void }
const AuthContext = createContext<AuthContextValue | null>(null)

async function requestToken(path: string, body: Credentials | Registration) {
  const response = await fetch(`/api/v1/auth/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? 'Authentication failed')
  return (await response.json() as { access_token: string }).access_token
}

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [token, setToken] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const router = useRouter()
  useEffect(() => { setToken(window.localStorage.getItem('fleet_token')); setReady(true) }, [])
  const value = useMemo<AuthContextValue>(() => ({
    token, ready,
    async login(input) { const next = await requestToken('login', input); window.localStorage.setItem('fleet_token', next); setToken(next); router.push('/dashboard') },
    async register(input) { const next = await requestToken('register', input); window.localStorage.setItem('fleet_token', next); setToken(next); router.push('/dashboard') },
    logout() { window.localStorage.removeItem('fleet_token'); setToken(null); router.push('/login') },
  }), [ready, router, token])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
