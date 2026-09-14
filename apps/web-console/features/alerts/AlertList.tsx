'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Alert = { id: number; kind: string; message: string; created_at: string; acknowledged: boolean }

export function AlertList() {
  const { token } = useAuth(); const [alerts, setAlerts] = useState<Alert[]>([])
  const load = async () => { const response = await fetch('/api/v1/alerts', { headers: { Authorization: `Bearer ${token}` } }); if (response.ok) setAlerts(await response.json()) }
  useEffect(() => { if (token) void load() }, [token])
  const acknowledge = async (id: number) => { await fetch(`/api/v1/alerts/${id}/acknowledge`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } }); await load() }
  return <section><div className="mb-8"><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Exceptions</p><h1 className="text-3xl font-bold tracking-tight">Alerts</h1><p className="mt-2 text-slate-500">Review and acknowledge fleet exceptions.</p></div><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><div className="space-y-3">{alerts.map((alert) => <div className="flex items-center justify-between gap-4 rounded-xl bg-mist p-4" key={alert.id}><div><div className="flex items-center gap-2"><span className="rounded-full bg-red-100 px-2 py-1 text-[10px] font-bold uppercase text-red-700">{alert.kind}</span><span className="text-xs text-slate-400">{new Date(alert.created_at).toLocaleString()}</span></div><p className="mt-2 text-sm font-semibold">{alert.message}</p></div>{!alert.acknowledged && <button className="rounded-lg bg-forest px-3 py-2 text-xs font-bold text-white" onClick={() => void acknowledge(alert.id)}>Acknowledge</button>}</div>)}{alerts.length === 0 && <div className="py-14 text-center text-sm text-slate-400">No alerts for this workspace.</div>}</div></div></section>
}
