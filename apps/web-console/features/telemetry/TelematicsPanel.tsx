'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Vehicle = { id: number; name: string; imei: string; protocol: string; overspeed_kph: number; idle_alert_minutes: number; immobilizer_schedule: string | null }
type TelematicsEvent = { kind: string; recorded_at: string; latitude: number; longitude: number; speed_kph: number }
type TelematicsData = { vehicle_id: number; events: TelematicsEvent[]; total_distance_m: number; engine_hours_s: number; avg_driver_score: number; total_trips: number }
type AutoTrip = { id: number; started_at: string; ended_at: string | null; distance_m: number; max_speed_kph: number; harsh_events: number; idle_seconds: number; driver_score: number }
type Reminder = { id: number; name: string; odometer_threshold_m: number | null; engine_hours_threshold_s: number | null; triggered: boolean }

const KIND_LABEL: Record<string, { label: string; cls: string }> = {
  harsh_braking: { label: 'Harsh brake', cls: 'bg-red-100 text-red-700' },
  harsh_acceleration: { label: 'Harsh accel', cls: 'bg-orange-100 text-orange-700' },
  harsh_cornering: { label: 'Harsh corner', cls: 'bg-yellow-100 text-yellow-700' },
  towing: { label: 'Towing', cls: 'bg-orange-200 text-orange-800' },
  jamming: { label: 'Jamming', cls: 'bg-purple-100 text-purple-700' },
  sos: { label: 'SOS', cls: 'bg-red-200 text-red-800' },
  crash: { label: 'CRASH', cls: 'bg-red-700 text-white' },
  door_open: { label: 'Door open', cls: 'bg-slate-200 text-slate-700' },
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
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(false)
  const [thresholds, setThresholds] = useState({ overspeed_kph: 120, idle_alert_minutes: 10, immobilizer_schedule: '' })
  const [thresholdSaving, setThresholdSaving] = useState(false)
  const [newReminder, setNewReminder] = useState({ name: '', odometer_km: '', engine_hours: '' })

  const selectedVehicle = vehicles.find(v => v.id === selected)

  useEffect(() => {
    if (!token) return
    void fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => {
        if (r.ok) {
          const rows = await r.json() as Vehicle[]
          setVehicles(rows)
          if (rows.length) {
            setSelected(rows[0].id)
            setThresholds({ overspeed_kph: rows[0].overspeed_kph, idle_alert_minutes: rows[0].idle_alert_minutes, immobilizer_schedule: rows[0].immobilizer_schedule ?? '' })
          }
        }
      })
  }, [token])

  useEffect(() => {
    if (!selected || !token) return
    const v = vehicles.find(v => v.id === selected)
    if (v) setThresholds({ overspeed_kph: v.overspeed_kph, idle_alert_minutes: v.idle_alert_minutes, immobilizer_schedule: v.immobilizer_schedule ?? '' })
    setLoading(true)
    Promise.all([
      fetch(`/api/v1/vehicles/${selected}/telematics`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : null),
      fetch(`/api/v1/vehicles/${selected}/auto-trips`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
      fetch(`/api/v1/vehicles/${selected}/reminders`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
    ]).then(([tel, tr, rem]) => {
      setData(tel as TelematicsData | null)
      setTrips(tr as AutoTrip[])
      setReminders(rem as Reminder[])
      setLoading(false)
    })
  }, [selected, token])

  const saveThresholds = async () => {
    if (!selected) return
    setThresholdSaving(true)
    const body: Record<string, unknown> = { overspeed_kph: thresholds.overspeed_kph, idle_alert_minutes: thresholds.idle_alert_minutes }
    if (thresholds.immobilizer_schedule.trim()) body.immobilizer_schedule = thresholds.immobilizer_schedule.trim()
    else body.immobilizer_schedule = null
    await fetch(`/api/v1/vehicles/${selected}/thresholds`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    })
    setVehicles(prev => prev.map(v => v.id === selected ? { ...v, ...body } as Vehicle : v))
    setThresholdSaving(false)
  }

  const addReminder = async () => {
    if (!selected || !newReminder.name) return
    const body: Record<string, unknown> = { name: newReminder.name }
    if (newReminder.odometer_km) body.odometer_threshold_m = parseFloat(newReminder.odometer_km) * 1000
    if (newReminder.engine_hours) body.engine_hours_threshold_s = parseFloat(newReminder.engine_hours) * 3600
    const res = await fetch(`/api/v1/vehicles/${selected}/reminders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    })
    if (res.ok) {
      const rem = await res.json() as Reminder
      setReminders(prev => [rem, ...prev])
      setNewReminder({ name: '', odometer_km: '', engine_hours: '' })
    }
  }

  const deleteReminder = async (id: number) => {
    if (!selected) return
    await fetch(`/api/v1/vehicles/${selected}/reminders/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
    setReminders(prev => prev.filter(r => r.id !== id))
  }

  return (
    <section>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Telematics</p>
        <h1 className="text-3xl font-bold tracking-tight">Driver behaviour & trips</h1>
        <p className="mt-2 text-slate-500">Harsh events, auto-detected trips, odometer, engine hours, fuel and maintenance reminders.</p>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {vehicles.map(v => (
          <button key={v.id}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${selected === v.id ? 'bg-forest text-white' : 'border border-slate-200 bg-white text-slate-700'}`}
            onClick={() => setSelected(v.id)}
          >{v.name}</button>
        ))}
      </div>

      {loading && <p className="py-12 text-center text-slate-400">Loading…</p>}

      {!loading && data && (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: 'Driver score', value: data.avg_driver_score.toFixed(0), sub: `avg over ${data.total_trips} trips`, cls: scoreColor(data.avg_driver_score) },
              { label: 'Total distance', value: (data.total_distance_m / 1000).toFixed(1), sub: 'km', cls: 'text-slate-800' },
              { label: 'Engine hours', value: (data.engine_hours_s / 3600).toFixed(1), sub: 'hours', cls: 'text-slate-800' },
              { label: 'Harsh events', value: String(data.events.length), sub: 'total recorded', cls: 'text-red-600' },
            ].map(c => (
              <div key={c.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400">{c.label}</p>
                <p className={`mt-2 text-4xl font-bold ${c.cls}`}>{c.value}</p>
                <p className="mt-1 text-xs text-slate-400">{c.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {/* Harsh events log */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
              <h2 className="text-lg font-bold">Events log</h2>
              <div className="mt-4 max-h-72 overflow-y-auto space-y-2">
                {data.events.length === 0 && <p className="py-8 text-center text-sm text-slate-400">No events recorded.</p>}
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
              <div className="mt-4 max-h-72 overflow-y-auto space-y-2">
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
                        {t.idle_seconds > 0 && <span className="text-blue-600">idle {Math.round(t.idle_seconds / 60)} min</span>}
                        {t.harsh_events > 0 && <span className="text-red-600">{t.harsh_events} harsh</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Alert thresholds */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
              <h2 className="text-lg font-bold">Alert thresholds</h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="block text-xs font-semibold text-slate-600">
                  Overspeed limit (km/h)
                  <input type="number" className="mt-1 w-full rounded-xl border border-slate-200 p-2.5" value={thresholds.overspeed_kph}
                    onChange={e => setThresholds(t => ({ ...t, overspeed_kph: Number(e.target.value) }))} />
                </label>
                <label className="block text-xs font-semibold text-slate-600">
                  Idle alert after (minutes)
                  <input type="number" className="mt-1 w-full rounded-xl border border-slate-200 p-2.5" value={thresholds.idle_alert_minutes}
                    onChange={e => setThresholds(t => ({ ...t, idle_alert_minutes: Number(e.target.value) }))} />
                </label>
                <label className="block text-xs font-semibold text-slate-600 sm:col-span-2">
                  Scheduled immobilizer (HH:MM-HH:MM, blank to disable)
                  <input className="mt-1 w-full rounded-xl border border-slate-200 p-2.5 font-mono" placeholder="e.g. 08:00-18:00"
                    value={thresholds.immobilizer_schedule}
                    onChange={e => setThresholds(t => ({ ...t, immobilizer_schedule: e.target.value }))} />
                </label>
              </div>
              <button className="mt-4 rounded-xl bg-forest px-5 py-2 text-sm font-bold text-white disabled:opacity-50"
                disabled={thresholdSaving} onClick={() => void saveThresholds()}>
                {thresholdSaving ? 'Saving…' : 'Save thresholds'}
              </button>
            </div>

            {/* Maintenance reminders */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
              <h2 className="text-lg font-bold">Maintenance reminders</h2>
              <div className="mt-4 space-y-2 max-h-40 overflow-y-auto">
                {reminders.length === 0 && <p className="text-sm text-slate-400">No reminders set.</p>}
                {reminders.map(r => (
                  <div key={r.id} className={`flex items-center justify-between rounded-xl px-4 py-2.5 ${r.triggered ? 'bg-red-50' : 'bg-slate-50'}`}>
                    <div>
                      <span className="text-sm font-semibold">{r.name}</span>
                      <span className="ml-2 text-xs text-slate-400">
                        {r.odometer_threshold_m ? `${(r.odometer_threshold_m / 1000).toFixed(0)} km` : ''}
                        {r.engine_hours_threshold_s ? ` / ${(r.engine_hours_threshold_s / 3600).toFixed(0)} h` : ''}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {r.triggered && <span className="text-xs font-bold text-red-600">DUE</span>}
                      <button className="text-xs text-red-400 hover:text-red-600" onClick={() => void deleteReminder(r.id)}>✕</button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                <input className="rounded-xl border border-slate-200 p-2 text-xs" placeholder="Name (e.g. Oil change)"
                  value={newReminder.name} onChange={e => setNewReminder(r => ({ ...r, name: e.target.value }))} />
                <input className="rounded-xl border border-slate-200 p-2 text-xs" placeholder="At km (e.g. 5000)"
                  value={newReminder.odometer_km} onChange={e => setNewReminder(r => ({ ...r, odometer_km: e.target.value }))} />
                <input className="rounded-xl border border-slate-200 p-2 text-xs" placeholder="At engine hours"
                  value={newReminder.engine_hours} onChange={e => setNewReminder(r => ({ ...r, engine_hours: e.target.value }))} />
              </div>
              <button className="mt-2 rounded-xl bg-forest px-4 py-2 text-xs font-bold text-white" onClick={() => void addReminder()}>
                Add reminder
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
