'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Vehicle = { id: number; name: string; imei: string; protocol: string }
type TelematicsEvent = { kind: string; recorded_at: string; latitude: number; longitude: number; speed_kph: number }
type TelematicsData = { vehicle_id: number; events: TelematicsEvent[]; total_distance_m: number; engine_hours_s: number; avg_driver_score: number; total_trips: number }
type AutoTrip = { id: number; started_at: string; ended_at: string | null; distance_m: number; max_speed_kph: number; harsh_events: number; driver_score: number; start_lat: number; start_lon: number; end_lat: number; end_lon: number }

const KIND_LABEL: Record<string, { label: string; cls: string }> = {
  harsh_braking: { label: 'Harsh brake', cls: 'bg-red-100 text-red-700' },
  harsh_acceleration: { label: 'Harsh accel', cls: 'bg-orange-100 text-orange-700' },
  harsh_cornering: { label: 'Harsh corner', cls: 'bg-yellow-100 text-yellow-700' },
  towing: { label: 'Towing', cls: 'bg-orange-200 text-orange-800' },
  jamming: { label: 'Jamming', cls: 'bg-purple-100 text-purple-700' },
  sos: { label: 'SOS', cls: 'bg-red-200 text-red-800' },
}

function scoreColor(score: number) {
  if (score >= 85) return 'text-green-700'
  if (score >= 65) return 'text-yellow-600'
  return 'text-red-600'
}

export function TelematicsPanel() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [data, setData] = useState<TelematicsData | null>(null)
  const [trips, setTrips] = useState<AutoTrip[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) return
    void fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => { if (r.ok) { const rows = await r.json() as Vehicle[]; setVehicles(rows); if (rows.length) setSelected(rows[0].id) } })
  }, [token])

  useEffect(() => {
    if (!selected || !token) return
    setLoading(true)
    Promise.all([
      fetch(`/api/v1/vehicles/${selected}/telematics`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : null),
      fetch(`/api/v1/vehicles/${selected}/auto-trips`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
    ]).then(([tel, tr]) => {
      setData(tel as TelematicsData | null)
      setTrips(tr as AutoTrip[])
      setLoading(false)
    })
  }, [selected, token])

  return (
    <section>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Telematics</p>
        <h1 className="text-3xl font-bold tracking-tight">Driver behaviour & trips</h1>
        <p className="mt-2 text-slate-500">Harsh events, auto-detected trips, odometer and engine hours from FMB920 IO data.</p>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {vehicles.map(v => (
          <button
            key={v.id}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${selected === v.id ? 'bg-forest text-white' : 'border border-slate-200 bg-white text-slate-700'}`}
            onClick={() => setSelected(v.id)}
          >
            {v.name}
          </button>
        ))}
      </div>

      {loading && <p className="py-12 text-center text-slate-400">Loading…</p>}

      {!loading && data && (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Driver score</p>
              <p className={`mt-2 text-4xl font-bold ${scoreColor(data.avg_driver_score)}`}>{data.avg_driver_score.toFixed(0)}</p>
              <p className="mt-1 text-xs text-slate-400">avg over {data.total_trips} trips</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Total distance</p>
              <p className="mt-2 text-4xl font-bold text-slate-800">{(data.total_distance_m / 1000).toFixed(1)}</p>
              <p className="mt-1 text-xs text-slate-400">km</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Engine hours</p>
              <p className="mt-2 text-4xl font-bold text-slate-800">{(data.engine_hours_s / 3600).toFixed(1)}</p>
              <p className="mt-1 text-xs text-slate-400">hours</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Harsh events</p>
              <p className="mt-2 text-4xl font-bold text-red-600">{data.events.length}</p>
              <p className="mt-1 text-xs text-slate-400">total recorded</p>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {/* Harsh events log */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
              <h2 className="text-lg font-bold">Harsh events log</h2>
              <div className="mt-4 max-h-80 overflow-y-auto space-y-2">
                {data.events.length === 0 && <p className="py-8 text-center text-sm text-slate-400">No harsh events recorded.</p>}
                {data.events.map((e, i) => {
                  const meta = KIND_LABEL[e.kind] ?? { label: e.kind, cls: 'bg-slate-100 text-slate-600' }
                  return (
                    <div key={i} className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-bold ${meta.cls}`}>{meta.label}</span>
                        <span className="text-xs text-slate-500">{new Date(e.recorded_at).toLocaleString()}</span>
                      </div>
                      <span className="text-xs text-slate-400">{e.speed_kph.toFixed(0)} km/h</span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Auto-detected trips */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
              <h2 className="text-lg font-bold">Auto-detected trips</h2>
              <div className="mt-4 max-h-80 overflow-y-auto space-y-2">
                {trips.filter(t => t.ended_at).length === 0 && <p className="py-8 text-center text-sm text-slate-400">No completed trips yet.</p>}
                {trips.filter(t => t.ended_at).map(t => {
                  const dur = Math.round((new Date(t.ended_at!).getTime() - new Date(t.started_at).getTime()) / 60000)
                  return (
                    <div key={t.id} className="rounded-xl bg-slate-50 px-4 py-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold">{new Date(t.started_at).toLocaleString()}</span>
                        <span className={`text-sm font-bold ${scoreColor(t.driver_score)}`}>{t.driver_score.toFixed(0)}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                        <span>{(t.distance_m / 1000).toFixed(2)} km</span>
                        <span>{dur} min</span>
                        <span>max {t.max_speed_kph.toFixed(0)} km/h</span>
                        {t.harsh_events > 0 && <span className="text-red-600">{t.harsh_events} harsh events</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
