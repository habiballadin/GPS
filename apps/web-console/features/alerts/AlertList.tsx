'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Alert = { id: number; vehicle_id: number; kind: string; message: string; created_at: string; acknowledged: boolean }
type Vehicle = { id: number; name: string }

const KIND_COLOR: Record<string, string> = {
  sos: 'bg-red-600 text-white',
  crash: 'bg-red-700 text-white',
  overspeed: 'bg-orange-500 text-white',
  harsh_braking: 'bg-red-100 text-red-700',
  harsh_acceleration: 'bg-orange-100 text-orange-700',
  harsh_cornering: 'bg-yellow-100 text-yellow-700',
  towing: 'bg-orange-200 text-orange-800',
  jamming: 'bg-purple-100 text-purple-700',
  idle: 'bg-blue-100 text-blue-700',
  ignition_on: 'bg-green-100 text-green-700',
  ignition_off: 'bg-slate-100 text-slate-600',
  geofence_enter: 'bg-teal-100 text-teal-700',
  geofence_exit: 'bg-teal-200 text-teal-800',
  low_battery: 'bg-yellow-200 text-yellow-800',
  low_external_power: 'bg-yellow-300 text-yellow-900',
  maintenance_due: 'bg-indigo-100 text-indigo-700',
  scheduled_immobilizer: 'bg-red-200 text-red-800',
  door_open: 'bg-slate-200 text-slate-700',
}

export function AlertList() {
  const { token } = useAuth()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [filterKind, setFilterKind] = useState('')
  const [filterVehicle, setFilterVehicle] = useState('')
  const [filterAck, setFilterAck] = useState<'all' | 'open' | 'acked'>('all')

  const load = async () => {
    const [ar, vr] = await Promise.all([
      fetch('/api/v1/alerts?limit=500', { headers: { Authorization: `Bearer ${token}` } }),
      fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } }),
    ])
    if (ar.ok) setAlerts(await ar.json())
    if (vr.ok) setVehicles(await vr.json())
  }

  useEffect(() => { if (token) void load() }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  const acknowledge = async (id: number) => {
    await fetch(`/api/v1/alerts/${id}/acknowledge`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, acknowledged: true } : a))
  }

  const acknowledgeAll = async () => {
    const unacked = filtered.filter(a => !a.acknowledged)
    await Promise.all(unacked.map(a => fetch(`/api/v1/alerts/${a.id}/acknowledge`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })))
    const ids = new Set(unacked.map(a => a.id))
    setAlerts(prev => prev.map(a => ids.has(a.id) ? { ...a, acknowledged: true } : a))
  }

  const kinds = Array.from(new Set(alerts.map(a => a.kind))).sort()
  const vehicleName = (id: number) => vehicles.find(v => v.id === id)?.name ?? `#${id}`

  const filtered = alerts.filter(a => {
    if (filterKind && a.kind !== filterKind) return false
    if (filterVehicle && String(a.vehicle_id) !== filterVehicle) return false
    if (filterAck === 'open' && a.acknowledged) return false
    if (filterAck === 'acked' && !a.acknowledged) return false
    return true
  })

  const openCount = alerts.filter(a => !a.acknowledged).length

  return (
    <section>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Exceptions</p>
          <h1 className="text-3xl font-bold tracking-tight">Alerts</h1>
          <p className="mt-2 text-slate-500">Review and acknowledge fleet exceptions.</p>
        </div>
        {openCount > 0 && (
          <span className="rounded-full bg-red-100 px-4 py-2 text-sm font-bold text-red-700">
            {openCount} open
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <select
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          value={filterAck}
          onChange={e => setFilterAck(e.target.value as 'all' | 'open' | 'acked')}
        >
          <option value="all">All alerts</option>
          <option value="open">Open only</option>
          <option value="acked">Acknowledged</option>
        </select>
        <select
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          value={filterKind}
          onChange={e => setFilterKind(e.target.value)}
        >
          <option value="">All types</option>
          {kinds.map(k => <option key={k} value={k}>{k.replace(/_/g, ' ')}</option>)}
        </select>
        <select
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
          value={filterVehicle}
          onChange={e => setFilterVehicle(e.target.value)}
        >
          <option value="">All vehicles</option>
          {vehicles.map(v => <option key={v.id} value={String(v.id)}>{v.name}</option>)}
        </select>
        {filtered.some(a => !a.acknowledged) && (
          <button
            className="rounded-xl bg-forest px-4 py-2 text-sm font-bold text-white"
            onClick={() => void acknowledgeAll()}
          >
            Acknowledge all ({filtered.filter(a => !a.acknowledged).length})
          </button>
        )}
        <span className="ml-auto self-center text-xs text-slate-400">{filtered.length} shown</span>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
        <div className="space-y-3">
          {filtered.map(alert => (
            <div
              key={alert.id}
              className={`flex items-center justify-between gap-4 rounded-xl p-4 ${alert.acknowledged ? 'bg-slate-50 opacity-60' : 'bg-mist'}`}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${KIND_COLOR[alert.kind] ?? 'bg-slate-200 text-slate-700'}`}>
                    {alert.kind.replace(/_/g, ' ')}
                  </span>
                  <span className="text-xs font-semibold text-forest">{vehicleName(alert.vehicle_id)}</span>
                  <span className="text-xs text-slate-400">{new Date(alert.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-1.5 text-sm font-semibold truncate">{alert.message}</p>
              </div>
              {!alert.acknowledged && (
                <button
                  className="shrink-0 rounded-lg bg-forest px-3 py-2 text-xs font-bold text-white"
                  onClick={() => void acknowledge(alert.id)}
                >
                  Ack
                </button>
              )}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="py-14 text-center text-sm text-slate-400">No alerts match the current filters.</div>
          )}
        </div>
      </div>
    </section>
  )
}
