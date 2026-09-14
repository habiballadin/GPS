'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { Map as LeafletMap, LayerGroup } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useAuth } from '@/components/providers/AuthProvider'

type Vehicle = { id: number; name: string; imei: string; protocol: string; last_seen_at?: string }
type Position = { vehicle_id: number; device_imei: string; recorded_at: string; latitude: number; longitude: number; speed_kph: number; heading: number; ignition: boolean; satellites: number }

function RealMap({ positions, vehicles }: { positions: Position[]; vehicles: Vehicle[] }) {
  const element = useRef<HTMLDivElement>(null); const map = useRef<LeafletMap | null>(null); const layer = useRef<LayerGroup | null>(null)
  useEffect(() => { let disposed = false; void import('leaflet').then(L => { if (disposed || !element.current || map.current) return; map.current = L.map(element.current).setView([20.5937, 78.9629], 5); L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 19 }).addTo(map.current); layer.current = L.layerGroup().addTo(map.current) }); return () => { disposed = true; map.current?.remove(); map.current = null } }, [])
  useEffect(() => { void import('leaflet').then(L => { if (!map.current || !layer.current) return; layer.current.clearLayers(); positions.forEach(position => L.circleMarker([position.latitude, position.longitude], { radius: 9, color: '#174b3c', fillColor: '#b7e35f', fillOpacity: 1, weight: 3 }).bindTooltip(vehicles.find(v => v.id === position.vehicle_id)?.name ?? position.device_imei).addTo(layer.current!)); if (positions.length === 1) map.current.setView([positions[0].latitude, positions[0].longitude], 13); else if (positions.length > 1) map.current.fitBounds(L.latLngBounds(positions.map(p => [p.latitude, p.longitude] as [number, number])), { padding: [30, 30] }) }) }, [positions, vehicles])
  return <div ref={element} className="min-h-[520px] w-full" />
}

export function LiveFleet() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    if (!token) return
    void fetch('/api/v1/vehicles', { headers: { Authorization: `Bearer ${token}` } }).then(async (response) => { if (response.ok) setVehicles(await response.json()) })
    const base = process.env.NEXT_PUBLIC_WS_URL ?? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
    const socket = new WebSocket(`${base}/api/v1/ws/live?token=${encodeURIComponent(token)}`)
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
    socket.onmessage = (event) => { const payload = JSON.parse(event.data) as { data?: Position[] }; setPositions(payload.data ?? []) }
    return () => socket.close()
  }, [token])
  const byVehicle = useMemo(() => new Map(positions.map((position) => [position.vehicle_id, position])), [positions])
  return <section><div className="mb-8 flex items-end justify-between"><div><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Telemetry</p><h1 className="text-3xl font-bold tracking-tight">Live operations</h1><p className="mt-2 text-slate-500">Current positions delivered by the custom TCP gateway.</p></div><span className={`rounded-full px-3 py-2 text-xs font-bold ${connected ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}>{connected ? '● Live stream connected' : '○ Waiting for stream'}</span></div><div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]"><div className="overflow-hidden rounded-2xl bg-[#dfe9dc] shadow-panel"><RealMap positions={positions} vehicles={vehicles} /></div><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><div className="flex items-center justify-between"><h2 className="text-lg font-bold">Vehicle signal</h2><span className="text-xs text-slate-400">{positions.length} live</span></div><div className="mt-4 space-y-3">{vehicles.map((vehicle) => { const position = byVehicle.get(vehicle.id); return <div className="rounded-xl bg-mist p-4" key={vehicle.id}><div className="flex items-center justify-between"><strong>{vehicle.name}</strong><span className={`text-xs font-bold ${position ? 'text-green-700' : 'text-slate-400'}`}>{position ? 'ONLINE' : 'OFFLINE'}</span></div><p className="mt-1 text-xs text-slate-500">{position ? `${position.speed_kph.toFixed(0)} km/h · ${position.satellites} satellites` : vehicle.imei}</p></div> })}{vehicles.length === 0 && <p className="py-8 text-center text-sm text-slate-400">No registered vehicles.</p>}</div></div></div></section>
}
