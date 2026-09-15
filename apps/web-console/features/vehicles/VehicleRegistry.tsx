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

const DEFAULT_FMB920_CONFIG = {
  apn: '',
  serverIp: '',
  port: '5001',
  heartbeat: '60',
  distance: '100',
  gprs: '1',
  sleepMode: '0',
  timezone: '0',
  ignition: '1',
  powerSaving: '0',
  sosNumber1: '',
  sosNumber2: '',
  sosEnabled: '1',
  overspeedLimit: '90',
  geofenceRadius: '200',
  movementAlert: '0',
  movementMinutes: '10',
  input1Mode: '0',
  input2Mode: '0',
  output1Mode: '0',
  output2Mode: '0',
  profile: 'standard',
}

const saveVehicleProfile = async (vehicleId: number, profile: string, config: typeof DEFAULT_FMB920_CONFIG, accessToken?: string | null) => {
  const token = accessToken ?? localStorage.getItem('gps_access_token')
  if (!token) return null

  const response = await fetch(`/api/v1/vehicles/${vehicleId}/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ profile, config: { ...config, profile: undefined } }),
  })

  if (!response.ok) {
    return null
  }

  return response.json()
}

const loadVehicleProfile = async (vehicleId: number, accessToken?: string | null) => {
  const token = accessToken ?? localStorage.getItem('gps_access_token')
  if (!token) return null

  const response = await fetch(`/api/v1/vehicles/${vehicleId}/profile`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    return null
  }

  return response.json() as Promise<{ profile?: string; config?: Partial<typeof DEFAULT_FMB920_CONFIG> } | null>
}

const deleteVehicleProfile = async (vehicleId: number, accessToken?: string | null) => {
  const token = accessToken ?? localStorage.getItem('gps_access_token')
  if (!token) return false

  const response = await fetch(`/api/v1/vehicles/${vehicleId}/profile`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })

  return response.ok
}

const FMB920_PROFILES: Record<string, Partial<typeof DEFAULT_FMB920_CONFIG>> = {
  standard: {
    heartbeat: '60',
    distance: '100',
    gprs: '1',
    sleepMode: '0',
    sosEnabled: '1',
    overspeedLimit: '90',
    geofenceRadius: '200',
    movementAlert: '1',
    movementMinutes: '10',
    powerSaving: '0',
  },
  heavyEquipment: {
    heartbeat: '30',
    distance: '50',
    gprs: '1',
    sleepMode: '0',
    sosEnabled: '1',
    overspeedLimit: '70',
    geofenceRadius: '100',
    movementAlert: '1',
    movementMinutes: '5',
    powerSaving: '0',
  },
  remoteAsset: {
    heartbeat: '180',
    distance: '250',
    gprs: '1',
    sleepMode: '1',
    sosEnabled: '1',
    overspeedLimit: '80',
    geofenceRadius: '500',
    movementAlert: '1',
    movementMinutes: '15',
    powerSaving: '1',
  },
}

function buildFmb920Commands(config: typeof DEFAULT_FMB920_CONFIG) {
  const commands: string[] = []

  if (config.apn.trim()) commands.push(`setparam 2001:${config.apn.trim()}`)
  if (config.serverIp.trim()) commands.push(`setparam 2004:${config.serverIp.trim()}`)
  if (config.port.trim()) commands.push(`setparam 2005:${config.port.trim()}`)
  if (config.gprs.trim()) commands.push(`setparam 2000:${config.gprs.trim()}`)
  if (config.heartbeat.trim()) commands.push(`setparam 3000:${config.heartbeat.trim()}`)
  if (config.distance.trim()) commands.push(`setparam 3001:${config.distance.trim()}`)
  if (config.sleepMode.trim()) commands.push(`setparam 3010:${config.sleepMode.trim()}`)
  if (config.timezone.trim()) commands.push(`setparam 2100:${config.timezone.trim()}`)
  if (config.ignition.trim()) commands.push(`setparam 4010:${config.ignition.trim()}`)
  if (config.powerSaving.trim()) commands.push(`setparam 3030:${config.powerSaving.trim()}`)
  if (config.sosEnabled.trim()) commands.push(`setparam 5001:${config.sosEnabled.trim()}`)
  if (config.sosNumber1.trim()) commands.push(`setparam 5002:${config.sosNumber1.trim()}`)
  if (config.sosNumber2.trim()) commands.push(`setparam 5003:${config.sosNumber2.trim()}`)
  if (config.overspeedLimit.trim()) commands.push(`setparam 3020:${config.overspeedLimit.trim()}`)
  if (config.geofenceRadius.trim()) commands.push(`setparam 3050:${config.geofenceRadius.trim()}`)
  if (config.movementAlert.trim()) commands.push(`setparam 3060:${config.movementAlert.trim()}`)
  if (config.movementMinutes.trim()) commands.push(`setparam 3061:${config.movementMinutes.trim()}`)
  if (config.input1Mode.trim()) commands.push(`setparam 4101:${config.input1Mode.trim()}`)
  if (config.input2Mode.trim()) commands.push(`setparam 4102:${config.input2Mode.trim()}`)
  if (config.output1Mode.trim()) commands.push(`setparam 4201:${config.output1Mode.trim()}`)
  if (config.output2Mode.trim()) commands.push(`setparam 4202:${config.output2Mode.trim()}`)

  return commands
}

export function VehicleRegistry() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [form, setForm] = useState({ name: '', imei: '', license_plate: '', protocol: 'teltonika' })
  const [message, setMessage] = useState('')
  const [cmdVehicleId, setCmdVehicleId] = useState<number | null>(null)
  const [command, setCommand] = useState('')
  const [cmdResult, setCmdResult] = useState<string | null>(null)
  const [cmdLoading, setCmdLoading] = useState(false)
  const [fmbConfig, setFmbConfig] = useState(DEFAULT_FMB920_CONFIG)
  const [configResult, setConfigResult] = useState<string | null>(null)
  const [configLoading, setConfigLoading] = useState(false)

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

  const sendSingleCommand = async (id: number, rawCommand: string) => {
    const res = await fetch(`/api/v1/vehicles/${id}/command`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ command: rawCommand }) })
    const data = await res.json().catch(() => ({}))
    return res.ok ? (data.response ?? 'sent') : (data.detail ?? 'error')
  }

  const sendCommand = async (id: number) => {
    if (!command.trim()) return
    setCmdLoading(true); setCmdResult(null)
    const value = await sendSingleCommand(id, command)
    setCmdResult(value)
    setCmdLoading(false)
  }

  const applyFmb920Config = async (id: number) => {
    const commands = buildFmb920Commands(fmbConfig)
    if (commands.length === 0) {
      setConfigResult('Add at least one setting value before applying.')
      return
    }

    setConfigLoading(true)
    setConfigResult(null)

    const lines: string[] = []
    for (const item of commands) {
      const result = await sendSingleCommand(id, item)
      lines.push(`${item} -> ${result}`)
    }

    await saveVehicleProfile(id, fmbConfig.profile || 'standard', fmbConfig, token)
    setConfigResult(lines.join('\n'))
    setConfigLoading(false)
  }

  const resetFmb920Config = async (id: number) => {
    const cleared = {
      ...DEFAULT_FMB920_CONFIG,
      profile: 'standard',
    }

    setFmbConfig(cleared)
    const deleted = await deleteVehicleProfile(id, token)
    if (deleted) {
      setConfigResult('Saved FMB920 profile cleared and reset to defaults.')
    } else {
      setConfigResult('Device profile was reset locally, but no saved backend profile was found.')
    }
  }

  const exportFmb920Profile = () => {
    const payload = {
      profile: fmbConfig.profile || 'standard',
      config: { ...fmbConfig, profile: undefined },
    }
    const json = JSON.stringify(payload, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `fmb920-profile-${cmdVehicle?.id ?? 'vehicle'}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    setConfigResult(`Exported profile JSON for ${cmdVehicle?.name ?? 'vehicle'} .`)
  }

  const importFmb920Profile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const text = await file.text()
    try {
      const parsed = JSON.parse(text) as { profile?: string; config?: Partial<typeof DEFAULT_FMB920_CONFIG> }
      const next = {
        ...DEFAULT_FMB920_CONFIG,
        ...parsed.config,
        profile: parsed.profile || 'standard',
      }
      setFmbConfig(next)
      setConfigResult(`Imported profile JSON: ${parsed.profile || 'standard'}`)
    } catch (error) {
      setConfigResult('Import failed: invalid JSON profile file.')
    } finally {
      event.target.value = ''
    }
  }

  const openVehicleCommandPanel = async (id: number) => {
    setCmdVehicleId(id)
    setCmdResult(null)
    setCommand('')
    const saved = await loadVehicleProfile(id, token)
    if (!saved) {
      setFmbConfig({ ...DEFAULT_FMB920_CONFIG, profile: 'standard' })
      return
    }

    const merged = {
      ...DEFAULT_FMB920_CONFIG,
      ...saved.config,
      profile: saved.profile || 'standard',
    }
    setFmbConfig(merged)
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
                          <button className="text-xs font-bold text-forest" onClick={() => void openVehicleCommandPanel(vehicle.id)}>
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

              <div className="mt-6 rounded-2xl border border-forest/20 bg-mist/40 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-bold">FMB920 config</h3>
                    <p className="text-xs text-slate-500">Common network and reporting settings</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="rounded-xl bg-forest px-4 py-2 text-xs font-bold text-white disabled:opacity-50"
                      disabled={configLoading}
                      onClick={() => void applyFmb920Config(cmdVehicle.id)}
                    >
                      {configLoading ? 'Applying...' : 'Apply config'}
                    </button>
                    <button
                      className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-600"
                      onClick={() => void resetFmb920Config(cmdVehicle.id)}
                    >
                      Reset profile
                    </button>
                    <button
                      className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-600"
                      onClick={exportFmb920Profile}
                    >
                      Export JSON
                    </button>
                    <label className="cursor-pointer rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-600">
                      Import JSON
                      <input type="file" accept="application/json" className="hidden" onChange={(event) => void importFmb920Profile(event)} />
                    </label>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {Object.entries(FMB920_PROFILES).map(([key, profile]) => (
                    <button
                      key={key}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold hover:bg-mist"
                      onClick={() => {
                        setFmbConfig((current) => ({ ...current, ...profile, profile: key }))
                        setConfigResult(`Loaded profile: ${key}`)
                      }}
                    >
                      {key === 'standard' ? 'Standard fleet' : key === 'heavyEquipment' ? 'Heavy equipment' : 'Remote asset'}
                    </button>
                  ))}
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="md:col-span-2">
                    <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Network settings</p>
                  </div>
                  <label className="block text-xs font-semibold text-slate-600">
                    APN
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.apn}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, apn: e.target.value }))}
                      placeholder="internet"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    GPRS
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.gprs}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, gprs: e.target.value }))}
                    >
                      <option value="1">Enabled</option>
                      <option value="0">Disabled</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Server IP
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.serverIp}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, serverIp: e.target.value }))}
                      placeholder="192.168.1.10"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Server port
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.port}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, port: e.target.value.replace(/\D/g, '') }))}
                      placeholder="5001"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Heartbeat (s)
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.heartbeat}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, heartbeat: e.target.value.replace(/\D/g, '') }))}
                      placeholder="60"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Min distance (m)
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.distance}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, distance: e.target.value.replace(/\D/g, '') }))}
                      placeholder="100"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Sleep mode
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.sleepMode}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, sleepMode: e.target.value }))}
                    >
                      <option value="0">Normal</option>
                      <option value="1">Sleep enabled</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Timezone offset
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.timezone}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, timezone: e.target.value.replace(/[^-\d]/g, '') }))}
                      placeholder="0"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Ignition detection
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.ignition}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, ignition: e.target.value }))}
                    >
                      <option value="1">Enabled</option>
                      <option value="0">Disabled</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Power save mode
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.powerSaving}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, powerSaving: e.target.value }))}
                    >
                      <option value="0">Normal</option>
                      <option value="1">Power save</option>
                    </select>
                  </label>

                  <div className="md:col-span-2">
                    <p className="mt-2 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">SOS / alarm settings</p>
                  </div>
                  <label className="block text-xs font-semibold text-slate-600">
                    SOS enabled
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.sosEnabled}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, sosEnabled: e.target.value }))}
                    >
                      <option value="1">Enabled</option>
                      <option value="0">Disabled</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    SOS number 1
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.sosNumber1}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, sosNumber1: e.target.value }))}
                      placeholder="+1 555 000 0001"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    SOS number 2
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.sosNumber2}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, sosNumber2: e.target.value }))}
                      placeholder="+1 555 000 0002"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Overspeed limit (km/h)
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.overspeedLimit}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, overspeedLimit: e.target.value.replace(/\D/g, '') }))}
                      placeholder="90"
                    />
                  </label>

                  <div className="md:col-span-2">
                    <p className="mt-2 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Geofence / movement alerts</p>
                  </div>
                  <label className="block text-xs font-semibold text-slate-600">
                    Geofence radius (m)
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.geofenceRadius}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, geofenceRadius: e.target.value.replace(/\D/g, '') }))}
                      placeholder="200"
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Movement alert
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.movementAlert}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, movementAlert: e.target.value }))}
                    >
                      <option value="0">Off</option>
                      <option value="1">On</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Movement window (minutes)
                    <input
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.movementMinutes}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, movementMinutes: e.target.value.replace(/\D/g, '') }))}
                      placeholder="10"
                    />
                  </label>

                  <div className="md:col-span-2">
                    <p className="mt-2 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">Input / output configuration</p>
                  </div>
                  <label className="block text-xs font-semibold text-slate-600">
                    Input 1 mode
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.input1Mode}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, input1Mode: e.target.value }))}
                    >
                      <option value="0">Normal</option>
                      <option value="1">SOS trigger</option>
                      <option value="2">Ignition sense</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Input 2 mode
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.input2Mode}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, input2Mode: e.target.value }))}
                    >
                      <option value="0">Normal</option>
                      <option value="1">SOS trigger</option>
                      <option value="2">Ignition sense</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Output 1 mode
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.output1Mode}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, output1Mode: e.target.value }))}
                    >
                      <option value="0">Disabled</option>
                      <option value="1">Pulse</option>
                      <option value="2">Alarm relay</option>
                    </select>
                  </label>
                  <label className="block text-xs font-semibold text-slate-600">
                    Output 2 mode
                    <select
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5"
                      value={fmbConfig.output2Mode}
                      onChange={(e) => setFmbConfig((current) => ({ ...current, output2Mode: e.target.value }))}
                    >
                      <option value="0">Disabled</option>
                      <option value="1">Pulse</option>
                      <option value="2">Alarm relay</option>
                    </select>
                  </label>
                </div>

                {configResult && (
                  <pre className="mt-4 rounded-xl bg-slate-900 p-3 text-xs font-mono text-slate-100 whitespace-pre-wrap">{configResult}</pre>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
