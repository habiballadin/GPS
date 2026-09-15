'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'
import { ExceptionCenter } from './ExceptionCenter'

type Summary = { total_vehicles: number; online_vehicles: number; offline_vehicles: number; open_alerts: number }

export function CommandCenter() {
  const { token } = useAuth()
  const [summary, setSummary] = useState<Summary | null>(null)
  useEffect(() => { if (!token) return; const load = async () => { const response = await fetch('/api/v1/dashboard/summary', { headers: { Authorization: `Bearer ${token}` } }); if (response.ok) setSummary(await response.json()) }; void load() }, [token])
  const cards = [['Vehicles online', summary ? String(summary.online_vehicles) : '—', summary ? `${summary.total_vehicles} registered` : 'Loading workspace'], ['Open alerts', summary ? String(summary.open_alerts) : '—', summary?.open_alerts ? 'Needs attention' : 'No active exceptions'], ['Vehicles offline', summary ? String(summary.offline_vehicles) : '—', 'Last seen threshold: 15 minutes'], ['Data freshness', summary ? 'Live' : '—', 'Connected to FastAPI']]
  return <section><div className="mb-8"><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Command center</p><h1 className="text-3xl font-bold tracking-tight">Good morning, operations team.</h1><p className="mt-2 text-slate-500">Your fleet signal, exceptions, and next actions in one place.</p></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{cards.map(([label, value, note]) => <article key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel"><p className="text-sm text-slate-500">{label}</p><p className="mt-4 text-4xl font-bold">{value}</p><p className="mt-2 text-xs text-slate-400">{note}</p></article>)}</div><div className="mt-6"><ExceptionCenter /></div><div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]"><div className="min-h-[360px] rounded-2xl bg-forest p-6 text-white"><p className="text-xs font-bold uppercase tracking-[0.18em] text-lime">Live fleet</p><h2 className="mt-3 text-2xl font-bold">Connect your first tracker</h2><p className="mt-2 max-w-md text-white/65">Register an IMEI, configure the custom Teltonika or CONCOX TCP endpoint, and the command center will begin showing live positions.</p><a href="/vehicles" className="mt-8 inline-block rounded-xl bg-lime px-4 py-3 text-sm font-bold text-forest">Register device</a></div><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Next actions</p><div className="mt-5 space-y-4"><a href="/vehicles" className="block rounded-xl bg-mist p-4 text-sm">Add a vehicle and IMEI</a><p className="rounded-xl bg-mist p-4 text-sm">Configure tracker APN and TCP port</p><p className="rounded-xl bg-mist p-4 text-sm">Run a live GPS test</p></div></div></div></section>
}
