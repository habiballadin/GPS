'use client'

import { FormEvent, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

export default function LoginPage() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [form, setForm] = useState({ organization_name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const submit = async (event: FormEvent) => { event.preventDefault(); setError(''); try { mode === 'login' ? await login(form) : await register(form) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to authenticate') } }
  return <main className="flex min-h-screen items-center justify-center bg-forest p-6"><section className="w-full max-w-md rounded-3xl bg-white p-8 shadow-panel"><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Fleet Operations</p><h1 className="mb-2 text-3xl font-bold">{mode === 'login' ? 'Welcome back' : 'Set up your fleet'}</h1><p className="mb-6 text-sm text-slate-500">{mode === 'login' ? 'Sign in to your operations workspace.' : 'Create a workspace to start tracking.'}</p><form className="space-y-4" onSubmit={submit}>{mode === 'register' && <label className="block text-sm font-semibold">Workspace name<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={form.organization_name} onChange={(event) => setForm({ ...form, organization_name: event.target.value })} required minLength={2} /></label>}<label className="block text-sm font-semibold">Work email<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label><label className="block text-sm font-semibold">Password<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required minLength={8} /></label>{error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}<button className="w-full rounded-xl bg-forest p-3 font-bold text-white" type="submit">{mode === 'login' ? 'Sign in' : 'Create workspace'}</button></form><button className="mt-5 w-full text-sm font-semibold text-forest" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create a new workspace' : 'Already have an account? Sign in'}</button></section></main>
}
