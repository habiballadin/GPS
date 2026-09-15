'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'
import type { Vehicle } from '@/types/domain'
import Link from 'next/link'

const PRESET_COMMANDS = [
  { label: 'Get GPRS status', cmd: 'getparam 2000' },
  { label: 'Enable GPRS', cmd: 'setparam 2000:1' },
  { label: 'Get server IP', cmd: 'getparam 2004' },
  { label: 'Get APN', cmd: 'getparam 2001' },
  { label: 'Reboot device', cmd: 'reboot' },
]

export function VehicleRegistry() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [form, setForm] = useState({ name: '', imei: '', license_plate: '', protocol: 'teltonika' })
  const [message, setMessage] = useState('')
  const [cmdVehicleId, setCmdVehicleId] = useState<number | null>(null)
  const [command, setCommand] = useState('')
  const [cmdResult, setCmdResult] = useState<string | null>(null)
  const [cmdLoading, setCmdLoading] = useState(false)

  const load = async () => {
    const response = await fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } })
    if (response.ok) {
      const rows = await response.json() as Array<{ id: number; name: string; imei: string; license_plate?: string; protocol: 'teltonika' | 'gt06'; active: boolean; last_seen_at?: string }>
      setVehicles(rows.map((row) => ({ id: row.id, organizationId: 0, name: row.name, imei: row.imei, protocol: row.protocol, status: row.active ? 'available' : 'out_of_service', lastSeenAt: row.last_seen_at })))
    }
  }

  useEffect(() => { if (token) void load() }, [token])

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const response = await fetch('/api/v1/vehicles', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(form) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not register device'); return }
    setForm({ name: '', imei: '', license_plate: '', protocol: 'teltonika' })
    setMessage('Device registered. Configure the tracker to connect to TCP 5001 or 5002.')
    await load()
  }

  const deactivate = async (id: number) => {
    if (!window.confirm('Deactivate this device?')) return
    await fetch(`/api/v1/vehicles/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
    await load()
  }

  const sendCommand = async (id: number) => {
    if (!command.trim()) return
    setCmdLoading(true); setCmdResult(null)
    const res = await fetch(`/api/v1/vehicles/${id}/command`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ command }) })
    const data = await res.json().catch(() => ({}))
    setCmdResult(res.ok ? (data.response ?? 'sent') : (data.detail ?? 'error'))
    setCmdLoading(false)
  }

  const cmdVehicle = vehicles.find((v) => v.id === cmdVehicleId)

  return (
    <section>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Fleet registry</p>
          <h1 className="text-3xl font-bold tracking-tight">Vehicles and devices</h1>
          <p className="mt-2 text-slate-500">Register the IMEI before powering on a tracker.</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <h2 className="text-lg font-bold">Add device</h2>
          <div className="mt-5 space-y-4">
            <label className="block text-sm font-semibold">Vehicle name
              <input className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </label>
            <label className="block text-sm font-semibold">IMEI
              <input className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={form.imei} onChange={(e) => setForm({ ...form, imei: e.target.value.replace(/\D/g, '') })} minLength={8} required />
            </label>
            <label className="block text-sm font-semibold">License plate
              <input className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={form.license_plate} onChange={(e) => setForm({ ...form, license_plate: e.target.value })} />
            </label>
            <label className="block text-sm font-semibold">Protocol
              <select className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={form.protocol} onChange={(e) => setForm({ ...form, protocol: e.target.value })}>
                <option value="teltonika">Teltonika FMB920 · TCP 5001</option>
                <option value="gt06">CONCOX V5 / GT06 · TCP 5002</option>
              </select>
            </label>
            {message && <p className="rounded-xl bg-mist p-3 text-sm text-forest">{message}</p>}
            <button className="w-full rounded-xl bg-forest p-3 font-bold text-white">Register device</button>
          </div>
        </form>

        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Registered devices</h2>
              <span className="rounded-full bg-mist px-3 py-1 text-xs font-bold text-forest">{vehicles.length} total</span>
            </div>
            <div className="mt-5 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="py-3">Vehicle</th>
                    <th>Protocol</th>
                    <th>Status</th>
                    <th>Last seen</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {vehicles.map((vehicle) => (
                    <tr className="border-b border-slate-100" key={vehicle.id}>
                      <td className="py-4">
                        <Link href={`/vehicles/${vehicle.id}`} className="font-bold text-forest hover:underline">{vehicle.name}</Link>
                        <small className="mt-1 block text-slate-400">{vehicle.imei}</small>
                      </td>
                      <td>{vehicle.protocol === 'teltonika' ? 'FMB920' : 'CONCOX V5'}</td>
                      <td>
                        <span className={`rounded-full px-2 py-1 text-xs font-semibold ${vehicle.lastSeenAt ? 'bg-green-50 text-green-700' : 'bg-slate-100 text-slate-500'}`}>
                          {vehicle.lastSeenAt ? 'Online' : 'Offline'}
                        </span>
                      </td>
                      <td>{vehicle.lastSeenAt ? new Date(vehicle.lastSeenAt).toLocaleString() : 'Never'}</td>
                      <td className="space-x-3">
                        <button className="text-xs font-bold text-red-600" onClick={() => void deactivate(vehicle.id)}>Deactivate</button>
                        {vehicle.protocol === 'teltonika' && (
                          <button className="text-xs font-bold text-forest" onClick={() => { setCmdVehicleId(vehicle.id); setCmdResult(null); setCommand('') }}>
                            Command
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {vehicles.length === 0 && (
                    <tr><td className="py-10 text-center text-slate-400" colSpan={5}>No devices registered yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {cmdVehicle && (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold">Send command — {cmdVehicle.name}</h2>
                <button className="text-xs text-slate-400 hover:text-slate-600" onClick={() => setCmdVehicleId(null)}>✕ Close</button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {PRESET_COMMANDS.map((p) => (
                  <button key={p.cmd} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold hover:bg-mist" onClick={() => setCommand(p.cmd)}>
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="mt-4 flex gap-2">
                <input
                  className="flex-1 rounded-xl border border-slate-200 p-3 font-mono text-sm"
                  placeholder="e.g. getparam 2000"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void sendCommand(cmdVehicle.id) }}
                />
                <button
                  className="rounded-xl bg-forest px-5 font-bold text-white disabled:opacity-50"
                  disabled={cmdLoading || !command.trim()}
                  onClick={() => void sendCommand(cmdVehicle.id)}
                >
                  {cmdLoading ? '...' : 'Send'}
                </button>
              </div>
              {cmdResult && (
                <pre className="mt-4 rounded-xl bg-slate-50 p-4 text-sm font-mono text-slate-700 whitespace-pre-wrap">{cmdResult}</pre>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
