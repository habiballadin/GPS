'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type ExceptionItem = { id: string; category: string; severity: string; title: string; detail: string; created_at: string; next_action: string; href: string }
const tone: Record<string, string> = { critical: 'bg-red-100 text-red-700', high: 'bg-orange-100 text-orange-700', medium: 'bg-amber-100 text-amber-700', low: 'bg-slate-100 text-slate-600' }

export function ExceptionCenter() {
  const { token } = useAuth(); const [items, setItems] = useState<ExceptionItem[]>([])
  useEffect(() => { if (!token) return; fetch('/api/v1/dashboard/exceptions', { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []).then(setItems) }, [token])
  return <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><div className="flex items-center justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Needs attention</p><h2 className="mt-2 text-xl font-bold">Exception center</h2></div><span className="rounded-full bg-mist px-3 py-1 text-sm font-bold text-forest">{items.length} open</span></div><div className="mt-5 space-y-3">{items.map(item => <article key={item.id} className="rounded-xl border border-slate-100 p-4"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-bold">{item.title}</h3><span className={`rounded-full px-2 py-1 text-[10px] font-bold uppercase ${tone[item.severity] ?? tone.medium}`}>{item.severity}</span><span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{item.category}</span></div><p className="mt-1 text-sm text-slate-500">{item.detail}</p><p className="mt-2 text-xs text-slate-400">Next: {item.next_action}</p></div><a href={item.href} className="shrink-0 rounded-lg bg-forest px-3 py-2 text-xs font-bold text-white">Open</a></div></article>)}{!items.length && <div className="rounded-xl bg-mist p-6 text-center text-sm text-forest">No open exceptions. The fleet is clear.</div>}</div></section>
}
