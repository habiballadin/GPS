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
  towing: boolean; jamming: boolean; sos: boolean
  ext_voltage_mv: number; battery_mv: number
}

function RealMap({ positions, vehicles }: { positions: Position[]; vehicles: Vehicle[] }) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<LeafletMap | null>(null)
  const layer = useRef<LayerGroup | null>(null)
  useEffect(() => {
    let disposed = false
    void import('leaflet').then(L => {
      if (disposed || !element.current || map.current) return
      map.current = L.map(element.current).setView([20.5937, 78.9629], 5)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 19 }).addTo(map.current)
      layer.current = L.layerGroup().addTo(map.current)
    })
    return () => { disposed = true; map.current?.remove(); map.current = null }
  }, [])
  useEffect(() => {
    void import('leaflet').then(L => {
      if (!map.current || !layer.current) return
      layer.current.clearLayers()
      positions.forEach(p => {
        const color = p.sos ? '#ef4444' : p.towing ? '#f97316' : p.jamming ? '#a855f7' : p.ignition ? '#b7e35f' : '#94a3b8'
        L.circleMarker([p.latitude, p.longitude], { radius: 9, color: '#174b3c', fillColor: color, fillOpacity: 1, weight: 3 })
          .bindTooltip(`${vehicles.find(v => v.id === p.vehicle_id)?.name ?? p.device_imei} · ${p.speed_kph.toFixed(0)} km/h`)
          .addTo(layer.current!)
      })
      if (positions.length === 1) map.current.setView([positions[0].latitude, positions[0].longitude], 13)
      else if (positions.length > 1) map.current.fitBounds(L.latLngBounds(positions.map(p => [p.latitude, p.longitude] as [number, number])), { padding: [30, 30] })
    })
  }, [positions, vehicles])
  return <div ref={element} className="min-h-[520px] w-full" />
}

export function LiveFleet() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [connected, setConnected] = useState(false)
  const [immobLoading, setImmobLoading] = useState<number | null>(null)
  const [immobResult, setImmobResult] = useState<Record<number, string>>({})

  useEffect(() => {
    if (!token) return
    void fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } }).then(async r => { if (r.ok) setVehicles(await r.json()) })
    const base = process.env.NEXT_PUBLIC_WS_URL ?? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    const socket = new WebSocket(`${base}/api/v1/ws/live?token=${encodeURIComponent(token)}`)
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
    socket.onmessage = (e) => { const payload = JSON.parse(e.data) as { data?: Position[] }; setPositions(payload.data ?? []) }
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

  return (
    <section>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Telemetry</p>
          <h1 className="text-3xl font-bold tracking-tight">Live operations</h1>
          <p className="mt-2 text-slate-500">Current positions delivered by the custom TCP gateway.</p>
        </div>
        <span className={`rounded-full px-3 py-2 text-xs font-bold ${connected ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}>
          {connected ? '● Live stream connected' : '○ Waiting for stream'}
        </span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <div className="overflow-hidden rounded-2xl bg-[#dfe9dc] shadow-panel">
          <RealMap positions={positions} vehicles={vehicles} />
          <div className="flex flex-wrap gap-3 p-3 text-xs text-slate-600">
            <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-[#b7e35f] border border-[#174b3c]" /> Ignition on</span>
            <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-slate-400 border border-[#174b3c]" /> Ignition off</span>
            <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-orange-400 border border-[#174b3c]" /> Towing</span>
            <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-purple-500 border border-[#174b3c]" /> Jamming</span>
            <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-red-500 border border-[#174b3c]" /> SOS</span>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Vehicle signal</h2>
            <span className="text-xs text-slate-400">{positions.length} live</span>
          </div>
          <div className="mt-4 space-y-3">
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
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {p.harsh_braking && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700">HARSH BRAKE</span>}
                        {p.harsh_acceleration && <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-bold text-orange-700">HARSH ACCEL</span>}
                        {p.harsh_cornering && <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-[10px] font-bold text-yellow-700">HARSH CORNER</span>}
                        {p.towing && <span className="rounded bg-orange-200 px-1.5 py-0.5 text-[10px] font-bold text-orange-800">TOWING</span>}
                        {p.jamming && <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700">JAMMING</span>}
                        {p.sos && <span className="rounded bg-red-200 px-1.5 py-0.5 text-[10px] font-bold text-red-800 animate-pulse">SOS</span>}
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
