'use client'

import { useEffect, useState, useMemo } from 'react'
import { useParams } from 'next/navigation'
import { useAuth } from '@/components/providers/AuthProvider'
import { RouteReplay, type ReplayPoint } from '@/features/telemetry/RouteReplay'

type Vehicle = {
  id: number; name: string; imei: string; protocol: string
  active: boolean; last_seen_at?: string; overspeed_kph?: number
}
type Activity = { id: string; type: string; title: string; status: string; occurred_at: string; detail: string }

function fmt(ms: number): string {
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export default function VehicleDetailPage() {
  const { token } = useAuth()
  const params = useParams<{ id: string }>()
  const [vehicle, setVehicle] = useState<Vehicle | null>(null)
  const [history, setHistory] = useState<ReplayPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [activity, setActivity] = useState<Activity[]>([])

  // Default range: last 24 hours
  const defaultSince = () => {
    const d = new Date(); d.setHours(d.getHours() - 24)
    return d.toISOString().slice(0, 16)
  }
  const [since, setSince] = useState(defaultSince)
  const [until, setUntil] = useState(() => new Date().toISOString().slice(0, 16))

  const fetchHistory = async (sinceVal: string, untilVal: string) => {
    if (!token) return
    setLoading(true)
    const headers = { Authorization: `Bearer ${token}` }
    const params_since = sinceVal ? `&since=${encodeURIComponent(new Date(sinceVal).toISOString())}` : ''
    const params_until = untilVal ? `&until=${encodeURIComponent(new Date(untilVal).toISOString())}` : ''
    const r = await fetch(`/api/v1/vehicles/${params.id}/history?limit=2000${params_since}${params_until}`, { headers })
    if (r.ok) setHistory(await r.json())
    setLoading(false)
  }

  useEffect(() => {
    if (!token) return
    void fetch(`/api/v1/vehicles/${params.id}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null).then(setVehicle)
    void fetchHistory(since, until)
    void fetch(`/api/v1/vehicles/${params.id}/activity?limit=100`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []).then(setActivity)
  }, [params.id, token]) // eslint-disable-line react-hooks/exhaustive-deps

  const stats = useMemo(() => {
    if (history.length < 2) return null
    let dist = 0, maxSpd = 0, sumSpd = 0
    for (let i = 1; i < history.length; i++) {
      const a = history[i - 1], b = history[i]
      const dLat = ((b.latitude - a.latitude) * Math.PI) / 180
      const dLon = ((b.longitude - a.longitude) * Math.PI) / 180
      const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * Math.PI / 180) * Math.cos(b.latitude * Math.PI / 180) * Math.sin(dLon / 2) ** 2
      const seg = 6_371_000 * 2 * Math.asin(Math.sqrt(s))
      if (seg < 50_000) dist += seg
      maxSpd = Math.max(maxSpd, b.speed_kph)
      sumSpd += b.speed_kph
    }
    const durationMs = new Date(history[history.length - 1].recorded_at).getTime() - new Date(history[0].recorded_at).getTime()
    return { dist, maxSpd, avgSpd: sumSpd / (history.length - 1), durationMs }
  }, [history])

  if (!vehicle) return <section><p className="text-slate-500">Loading vehicle…</p></section>

  return (
    <section>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Fleet detail</p>
        <h1 className="text-3xl font-bold tracking-tight">{vehicle.name}</h1>
        <p className="mt-2 text-slate-500">
          {vehicle.imei} · {vehicle.protocol === 'teltonika' ? 'FMB920' : 'CONCOX V5'} ·{' '}
          {vehicle.active ? 'Active' : 'Inactive'} ·{' '}
          Last seen: {vehicle.last_seen_at ? new Date(vehicle.last_seen_at).toLocaleString() : 'Never'}
        </p>
      </div>

      {/* Date range picker */}
      <div className="mb-5 flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-panel">
        <label className="block text-xs font-semibold text-slate-600">
          From
          <input
            type="datetime-local"
            className="mt-1 block rounded-xl border border-slate-200 p-2 text-sm"
            value={since}
            onChange={e => setSince(e.target.value)}
          />
        </label>
        <label className="block text-xs font-semibold text-slate-600">
          To
          <input
            type="datetime-local"
            className="mt-1 block rounded-xl border border-slate-200 p-2 text-sm"
            value={until}
            onChange={e => setUntil(e.target.value)}
          />
        </label>
        <button
          className="rounded-xl bg-forest px-5 py-2 text-sm font-bold text-white disabled:opacity-50"
          disabled={loading}
          onClick={() => void fetchHistory(since, until)}
        >
          {loading ? 'Loading…' : 'Load route'}
        </button>
        {/* Quick presets */}
        {[['1h', 1], ['6h', 6], ['24h', 24], ['7d', 168]].map(([label, hours]) => (
          <button
            key={label}
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-mist"
            onClick={() => {
              const s = new Date(); s.setHours(s.getHours() - Number(hours))
              const sv = s.toISOString().slice(0, 16)
              const uv = new Date().toISOString().slice(0, 16)
              setSince(sv); setUntil(uv)
              void fetchHistory(sv, uv)
            }}
          >
            Last {label}
          </button>
        ))}
        <span className="ml-auto self-center text-xs text-slate-400">{history.length} points</span>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: 'Distance', value: (stats.dist / 1000).toFixed(2), unit: 'km' },
            { label: 'Duration', value: fmt(stats.durationMs), unit: '' },
            { label: 'Max speed', value: stats.maxSpd.toFixed(0), unit: 'km/h' },
            { label: 'Avg speed', value: stats.avgSpd.toFixed(0), unit: 'km/h' },
          ].map(c => (
            <div key={c.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">{c.label}</p>
              <p className="mt-2 text-3xl font-bold text-slate-800">{c.value}</p>
              {c.unit && <p className="mt-1 text-xs text-slate-400">{c.unit}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Route replay */}
      <RouteReplay points={history} overspeedKph={vehicle.overspeed_kph ?? 120} />
      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Vehicle history</p><h2 className="mt-2 text-xl font-bold">Operational timeline</h2></div><span className="rounded-full bg-mist px-3 py-1 text-xs font-bold text-forest">{activity.length} events</span></div><div className="mt-5 space-y-4">{activity.map(item => <article className="flex gap-4" key={item.id}><div className="mt-1 h-3 w-3 shrink-0 rounded-full bg-forest ring-4 ring-lime/30" /><div className="min-w-0 flex-1 border-b border-slate-100 pb-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{item.type}</span><h3 className="font-bold">{item.title}</h3></div><span className="rounded-full bg-mist px-2 py-1 text-[10px] font-bold uppercase text-forest">{item.status}</span></div><p className="mt-1 text-sm text-slate-500">{item.detail}</p><time className="mt-2 block text-xs text-slate-400">{new Date(item.occurred_at).toLocaleString()}</time></div></article>)}{!activity.length && <p className="py-8 text-center text-sm text-slate-400">No operational history recorded yet.</p>}</div></div>
    </section>
  )
}
