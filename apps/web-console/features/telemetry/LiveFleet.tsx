'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { Map as LeafletMap, LayerGroup } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useAuth } from '@/components/providers/AuthProvider'

type Vehicle = { id: number; name: string; imei: string; protocol: string; last_seen_at?: string }
type Position = {
  vehicle_id: number; device_imei: string; recorded_at: string
  latitude: number; longitude: number; speed_kph: number; heading: number
  ignition: boolean; satellites: number
  harsh_braking: boolean; harsh_acceleration: boolean; harsh_cornering: boolean
  towing: boolean; jamming: boolean; sos: boolean; crash: boolean; door_open: boolean
  ext_voltage_mv: number; battery_mv: number; fuel_level: number
}
type WsAlert = { kind: string; vehicle_id: number; message: string; created_at: string }
type TrailMap = Record<number, Position[]>

const ALERT_COLORS: Record<string, string> = {
  sos: 'bg-red-600 text-white',
  crash: 'bg-red-700 text-white',
  overspeed: 'bg-orange-500 text-white',
  harsh_braking: 'bg-red-100 text-red-800',
  harsh_acceleration: 'bg-orange-100 text-orange-800',
  harsh_cornering: 'bg-yellow-100 text-yellow-800',
  towing: 'bg-orange-200 text-orange-900',
  jamming: 'bg-purple-100 text-purple-800',
  idle: 'bg-blue-100 text-blue-800',
  ignition_on: 'bg-green-100 text-green-800',
  ignition_off: 'bg-slate-100 text-slate-700',
  geofence_enter: 'bg-teal-100 text-teal-800',
  geofence_exit: 'bg-teal-200 text-teal-900',
  low_battery: 'bg-yellow-200 text-yellow-900',
  low_external_power: 'bg-yellow-300 text-yellow-900',
  maintenance_due: 'bg-indigo-100 text-indigo-800',
  scheduled_immobilizer: 'bg-red-200 text-red-900',
  door_open: 'bg-slate-200 text-slate-800',
}

function RealMap({ positions, trails, vehicles }: { positions: Position[]; trails: TrailMap; vehicles: Vehicle[] }) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<LeafletMap | null>(null)
  const markerLayer = useRef<LayerGroup | null>(null)
  const trailLayer = useRef<LayerGroup | null>(null)

  useEffect(() => {
    let disposed = false
    void import('leaflet').then(L => {
      if (disposed || !element.current || map.current) return
      map.current = L.map(element.current).setView([20.5937, 78.9629], 5)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 19 }).addTo(map.current)
      trailLayer.current = L.layerGroup().addTo(map.current)
      markerLayer.current = L.layerGroup().addTo(map.current)
    })
    return () => { disposed = true; map.current?.remove(); map.current = null }
  }, [])

  useEffect(() => {
    void import('leaflet').then(L => {
      if (!map.current || !markerLayer.current || !trailLayer.current) return
      markerLayer.current.clearLayers()
      trailLayer.current.clearLayers()

      // Draw trails
      Object.entries(trails).forEach(([vidStr, pts]) => {
        if (pts.length < 2) return
        const coords = pts.map(p => [p.latitude, p.longitude] as [number, number])
        L.polyline(coords, { color: '#174b3c', weight: 3, opacity: 0.5 }).addTo(trailLayer.current!)
      })

      // Draw markers
      positions.forEach(p => {
        const color = p.sos ? '#ef4444' : p.crash ? '#b91c1c' : p.towing ? '#f97316' : p.jamming ? '#a855f7' : p.ignition ? '#b7e35f' : '#94a3b8'
        const name = vehicles.find(v => v.id === p.vehicle_id)?.name ?? p.device_imei
        L.circleMarker([p.latitude, p.longitude], { radius: 9, color: '#174b3c', fillColor: color, fillOpacity: 1, weight: 3 })
          .bindTooltip(`${name} · ${p.speed_kph.toFixed(0)} km/h`)
          .addTo(markerLayer.current!)
      })

      if (positions.length === 1) map.current.setView([positions[0].latitude, positions[0].longitude], 13)
      else if (positions.length > 1) map.current.fitBounds(L.latLngBounds(positions.map(p => [p.latitude, p.longitude] as [number, number])), { padding: [30, 30] })
    })
  }, [positions, trails, vehicles])

  return <div ref={element} className="min-h-[520px] w-full" />
}

export function LiveFleet() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [trails, setTrails] = useState<TrailMap>({})
  const [connected, setConnected] = useState(false)
  const [alerts, setAlerts] = useState<(WsAlert & { id: number })[]>([])
  const [immobLoading, setImmobLoading] = useState<number | null>(null)
  const [immobResult, setImmobResult] = useState<Record<number, string>>({})
  const [etaVehicle, setEtaVehicle] = useState<number | null>(null)
  const [etaDest, setEtaDest] = useState({ lat: '', lon: '' })
  const [etaResult, setEtaResult] = useState<string | null>(null)
  const alertIdRef = useRef(0)

  useEffect(() => {
    if (!token) return
    void fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => { if (r.ok) setVehicles(await r.json()) })

    const base = process.env.NEXT_PUBLIC_WS_URL ?? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    const socket = new WebSocket(`${base}/api/v1/ws/live?token=${encodeURIComponent(token)}`)
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
    socket.onmessage = (e) => {
      const payload = JSON.parse(e.data) as { type: string; data?: Position[]; trails?: TrailMap; alert?: WsAlert }
      if (payload.type === 'positions') {
        setPositions(payload.data ?? [])
        if (payload.trails) setTrails(payload.trails)
      } else if (payload.type === 'alert' && payload.data) {
        const alert = payload.data as unknown as WsAlert
        const id = ++alertIdRef.current
        setAlerts(prev => [{ ...alert, id }, ...prev].slice(0, 20))
        setTimeout(() => setAlerts(prev => prev.filter(a => a.id !== id)), 8000)
      }
    }
    return () => socket.close()
  }, [token])

  const byVehicle = useMemo(() => new Map(positions.map(p => [p.vehicle_id, p])), [positions])

  const toggleImmobilizer = async (vehicleId: number, enable: boolean) => {
    setImmobLoading(vehicleId)
    const res = await fetch(`/api/v1/vehicles/${vehicleId}/immobilizer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ enable }),
    })
    const data = await res.json().catch(() => ({})) as { response?: string; detail?: string }
    setImmobResult(prev => ({ ...prev, [vehicleId]: res.ok ? (data.response ?? 'done') : (data.detail ?? 'error') }))
    setImmobLoading(null)
  }

  const calcEta = async () => {
    if (!etaVehicle || !etaDest.lat || !etaDest.lon) return
    const res = await fetch(`/api/v1/vehicles/${etaVehicle}/eta`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ dest_lat: parseFloat(etaDest.lat), dest_lon: parseFloat(etaDest.lon) }),
    })
    const data = await res.json().catch(() => ({})) as { distance_m?: number; eta_minutes?: number; speed_kph?: number }
    if (res.ok) setEtaResult(`${(data.distance_m! / 1000).toFixed(1)} km · ${data.eta_minutes} min at ${data.speed_kph?.toFixed(0)} km/h`)
    else setEtaResult('Error calculating ETA')
  }

  return (
    <section>
      {/* Real-time alert toasts */}
      <div className="fixed bottom-4 right-4 z-50 space-y-2 w-80">
        {alerts.map(a => {
          const cls = ALERT_COLORS[a.kind] ?? 'bg-slate-800 text-white'
          const vname = vehicles.find(v => v.id === a.vehicle_id)?.name ?? `#${a.vehicle_id}`
          return (
            <div key={a.id} className={`rounded-xl px-4 py-3 shadow-lg text-sm font-semibold ${cls} animate-in slide-in-from-right`}>
              <span className="font-bold">{vname}</span> — {a.message}
            </div>
          )
        })}
      </div>

      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Telemetry</p>
          <h1 className="text-3xl font-bold tracking-tight">Live operations</h1>
          <p className="mt-2 text-slate-500">Positions, trails and real-time alerts from the TCP gateway.</p>
        </div>
        <span className={`rounded-full px-3 py-2 text-xs font-bold ${connected ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}>
          {connected ? '● Live' : '○ Connecting'}
        </span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <div className="space-y-3">
          <div className="overflow-hidden rounded-2xl bg-[#dfe9dc] shadow-panel">
            <RealMap positions={positions} trails={trails} vehicles={vehicles} />
            <div className="flex flex-wrap gap-3 p-3 text-xs text-slate-600">
              {[['#b7e35f','Ignition on'],['#94a3b8','Ignition off'],['#f97316','Towing'],['#a855f7','Jamming'],['#ef4444','SOS'],['#b91c1c','Crash']].map(([c,l]) => (
                <span key={l} className="flex items-center gap-1">
                  <span className="inline-block h-3 w-3 rounded-full border border-[#174b3c]" style={{ background: c }} /> {l}
                </span>
              ))}
            </div>
          </div>

          {/* ETA calculator */}
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-panel">
            <h3 className="text-sm font-bold mb-3">ETA calculator</h3>
            <div className="flex flex-wrap gap-2 items-end">
              <select className="rounded-xl border border-slate-200 p-2 text-sm" value={etaVehicle ?? ''} onChange={e => setEtaVehicle(Number(e.target.value))}>
                <option value="">Select vehicle</option>
                {vehicles.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
              <input className="rounded-xl border border-slate-200 p-2 text-sm w-28" placeholder="Dest lat" value={etaDest.lat} onChange={e => setEtaDest(d => ({ ...d, lat: e.target.value }))} />
              <input className="rounded-xl border border-slate-200 p-2 text-sm w-28" placeholder="Dest lon" value={etaDest.lon} onChange={e => setEtaDest(d => ({ ...d, lon: e.target.value }))} />
              <button className="rounded-xl bg-forest px-4 py-2 text-sm font-bold text-white" onClick={() => void calcEta()}>Calculate</button>
              {etaResult && <span className="text-sm text-slate-600">{etaResult}</span>}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Vehicle signal</h2>
            <span className="text-xs text-slate-400">{positions.length} live</span>
          </div>
          <div className="mt-4 space-y-3 max-h-[700px] overflow-y-auto">
            {vehicles.map(vehicle => {
              const p = byVehicle.get(vehicle.id)
              return (
                <div className="rounded-xl bg-mist p-4" key={vehicle.id}>
                  <div className="flex items-center justify-between">
                    <strong>{vehicle.name}</strong>
                    <span className={`text-xs font-bold ${p ? 'text-green-700' : 'text-slate-400'}`}>{p ? 'ONLINE' : 'OFFLINE'}</span>
                  </div>
                  {p ? (
                    <>
                      <p className="mt-1 text-xs text-slate-500">
                        {p.speed_kph.toFixed(0)} km/h · {p.satellites} sats · {p.ignition ? '🔑 IGN ON' : '⭕ IGN OFF'}
                        {p.ext_voltage_mv > 0 && ` · ${(p.ext_voltage_mv / 1000).toFixed(1)}V`}
                        {p.fuel_level > 0 && ` · Fuel: ${p.fuel_level}`}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {p.harsh_braking && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700">HARSH BRAKE</span>}
                        {p.harsh_acceleration && <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-bold text-orange-700">HARSH ACCEL</span>}
                        {p.harsh_cornering && <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-[10px] font-bold text-yellow-700">HARSH CORNER</span>}
                        {p.towing && <span className="rounded bg-orange-200 px-1.5 py-0.5 text-[10px] font-bold text-orange-800">TOWING</span>}
                        {p.jamming && <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700">JAMMING</span>}
                        {p.sos && <span className="rounded bg-red-200 px-1.5 py-0.5 text-[10px] font-bold text-red-800 animate-pulse">SOS</span>}
                        {p.crash && <span className="rounded bg-red-700 px-1.5 py-0.5 text-[10px] font-bold text-white animate-pulse">CRASH</span>}
                        {p.door_open && <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-700">DOOR OPEN</span>}
                      </div>
                      {vehicle.protocol === 'teltonika' && (
                        <div className="mt-3 flex items-center gap-2">
                          <button
                            className="rounded-lg bg-red-600 px-3 py-1 text-xs font-bold text-white disabled:opacity-50"
                            disabled={immobLoading === vehicle.id}
                            onClick={() => void toggleImmobilizer(vehicle.id, true)}
                          >
                            {immobLoading === vehicle.id ? '...' : 'Cut engine'}
                          </button>
                          <button
                            className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-bold text-slate-700 disabled:opacity-50"
                            disabled={immobLoading === vehicle.id}
                            onClick={() => void toggleImmobilizer(vehicle.id, false)}
                          >
                            Restore
                          </button>
                          {immobResult[vehicle.id] && <span className="text-xs text-slate-500">{immobResult[vehicle.id]}</span>}
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="mt-1 text-xs text-slate-400">{vehicle.imei}</p>
                  )}
                </div>
              )
            })}
            {vehicles.length === 0 && <p className="py-8 text-center text-sm text-slate-400">No registered vehicles.</p>}
          </div>
        </div>
      </div>
    </section>
  )
}
