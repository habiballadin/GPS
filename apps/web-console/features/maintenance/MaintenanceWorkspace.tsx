'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Vehicle = { id: number; name: string; license_plate?: string }
type Defect = { id: number; vehicle_id: number; title: string; severity: string; status: string; reported_at: string }
type WorkOrder = { id: number; vehicle_id: number; defect_id?: number; vendor_id?: number; title: string; priority: string; status: string; due_at?: string; total_cost: number; downtime_started_at?: string; downtime_ended_at?: string }
type ServicePlan = { id: number; vehicle_id: number; name: string; interval_distance_m?: number; interval_engine_hours_s?: number; due: boolean; due_reason?: string }
type Part = { id: number; name: string; sku: string; quantity_on_hand: number; reorder_level: number; unit_cost: number; low_stock: boolean }
type Vendor = { id: number; name: string; contact_name?: string; phone?: string }
type Prediction = { vehicle_id: number; vehicle_name: string; risk_score: number; risk_level: string; predicted_failure_window_days?: number; maintenance_due: boolean; factors: string[]; recommended_actions: string[] }

const headers = (token: string | null) => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token}` })
const money = (value: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value)

export function MaintenanceWorkspace() {
  const { token } = useAuth()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [defects, setDefects] = useState<Defect[]>([])
  const [orders, setOrders] = useState<WorkOrder[]>([])
  const [plans, setPlans] = useState<ServicePlan[]>([])
  const [parts, setParts] = useState<Part[]>([])
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [message, setMessage] = useState('')
  const [inspection, setInspection] = useState({ vehicle_id: '', inspection_type: 'pre_trip', notes: '', defect_title: '', severity: 'minor' })
  const [order, setOrder] = useState({ vehicle_id: '', defect_id: '', vendor_id: '', title: '', priority: 'medium', due_at: '', labor_cost: '0', parts_cost: '0', external_cost: '0' })
  const [plan, setPlan] = useState({ vehicle_id: '', name: '', interval_km: '', interval_hours: '' })
  const [part, setPart] = useState({ name: '', sku: '', quantity_on_hand: '', reorder_level: '', unit_cost: '' })
  const [partUse, setPartUse] = useState({ work_order_id: '', part_id: '', quantity: '1' })
  const [vendor, setVendor] = useState({ name: '', contact_name: '', phone: '', email: '' })

  const load = async () => {
    if (!token) return
    const auth = { Authorization: `Bearer ${token}` }
    const [vehicleRes, defectRes, orderRes, planRes, partRes, vendorRes, predictionRes] = await Promise.all([
      fetch('/api/v1/vehicles', { headers: auth }), fetch('/api/v1/defects?status=open', { headers: auth }), fetch('/api/v1/work-orders', { headers: auth }), fetch('/api/v1/service-plans', { headers: auth }), fetch('/api/v1/parts', { headers: auth }), fetch('/api/v1/vendors', { headers: auth }), fetch('/api/v1/maintenance/predictions', { headers: auth }),
    ])
    if (vehicleRes.ok) setVehicles(await vehicleRes.json())
    if (defectRes.ok) setDefects(await defectRes.json())
    if (orderRes.ok) setOrders(await orderRes.json())
    if (planRes.ok) setPlans(await planRes.json())
    if (partRes.ok) setParts(await partRes.json())
    if (vendorRes.ok) setVendors(await vendorRes.json())
    if (predictionRes.ok) setPredictions(await predictionRes.json())
  }
  useEffect(() => { void load() }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  const submitInspection = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const defects = inspection.defect_title.trim() ? [{ title: inspection.defect_title.trim(), severity: inspection.severity }] : []
    const response = await fetch('/api/v1/inspections', { method: 'POST', headers: headers(token), body: JSON.stringify({ vehicle_id: Number(inspection.vehicle_id), inspection_type: inspection.inspection_type, notes: inspection.notes || null, defects }) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not submit inspection'); return }
    setInspection({ vehicle_id: '', inspection_type: 'pre_trip', notes: '', defect_title: '', severity: 'minor' }); setMessage('Inspection submitted.'); await load()
  }

  const submitWorkOrder = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const response = await fetch('/api/v1/work-orders', { method: 'POST', headers: headers(token), body: JSON.stringify({ vehicle_id: Number(order.vehicle_id), defect_id: order.defect_id ? Number(order.defect_id) : null, vendor_id: order.vendor_id ? Number(order.vendor_id) : null, title: order.title, priority: order.priority, due_at: order.due_at ? new Date(order.due_at).toISOString() : null, labor_cost: Number(order.labor_cost), parts_cost: Number(order.parts_cost), external_cost: Number(order.external_cost) }) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not create work order'); return }
    setOrder({ vehicle_id: '', defect_id: '', vendor_id: '', title: '', priority: 'medium', due_at: '', labor_cost: '0', parts_cost: '0', external_cost: '0' }); setMessage('Work order created.'); await load()
  }

  const complete = async (id: number) => {
    const response = await fetch(`/api/v1/work-orders/${id}`, { method: 'PATCH', headers: headers(token), body: JSON.stringify({ status: 'completed' }) })
    setMessage(response.ok ? 'Work order completed and linked defect resolved.' : 'Could not complete work order')
    if (response.ok) await load()
  }

  const submitPlan = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const response = await fetch('/api/v1/service-plans', { method: 'POST', headers: headers(token), body: JSON.stringify({ vehicle_id: Number(plan.vehicle_id), name: plan.name, interval_distance_m: plan.interval_km ? Number(plan.interval_km) * 1000 : null, interval_engine_hours_s: plan.interval_hours ? Number(plan.interval_hours) * 3600 : null }) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not create service plan'); return }
    setPlan({ vehicle_id: '', name: '', interval_km: '', interval_hours: '' }); setMessage('Service plan created.'); await load()
  }

  const createDueOrder = async (id: number) => {
    const response = await fetch(`/api/v1/service-plans/${id}/work-orders`, { method: 'POST', headers: headers(token) })
    setMessage(response.ok ? 'Due service work order created.' : (await response.json().catch(() => null))?.detail ?? 'Could not create due work order')
    if (response.ok) await load()
  }

  const submitPart = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const response = await fetch('/api/v1/parts', { method: 'POST', headers: headers(token), body: JSON.stringify({ ...part, quantity_on_hand: Number(part.quantity_on_hand), reorder_level: Number(part.reorder_level || 0), unit_cost: Number(part.unit_cost || 0) }) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not add part'); return }
    setPart({ name: '', sku: '', quantity_on_hand: '', reorder_level: '', unit_cost: '' }); setMessage('Part added to inventory.'); await load()
  }

  const assignPart = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const response = await fetch(`/api/v1/work-orders/${partUse.work_order_id}/parts`, { method: 'POST', headers: headers(token), body: JSON.stringify({ part_id: Number(partUse.part_id), quantity: Number(partUse.quantity) }) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not reserve part'); return }
    setPartUse({ work_order_id: '', part_id: '', quantity: '1' }); setMessage('Part reserved for work order; stock will be consumed on completion.'); await load()
  }

  const submitVendor = async (event: FormEvent) => {
    event.preventDefault(); setMessage('')
    const response = await fetch('/api/v1/vendors', { method: 'POST', headers: headers(token), body: JSON.stringify(vendor) })
    if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not add vendor'); return }
    setVendor({ name: '', contact_name: '', phone: '', email: '' }); setMessage('Vendor added.'); await load()
  }

  const toggleDowntime = async (workOrder: WorkOrder) => {
    const endpoint = workOrder.downtime_started_at && !workOrder.downtime_ended_at ? 'stop' : 'start'
    const response = await fetch(`/api/v1/work-orders/${workOrder.id}/downtime/${endpoint}`, { method: 'POST', headers: headers(token) })
    setMessage(response.ok ? `Downtime ${endpoint}ed.` : 'Could not update downtime')
    if (response.ok) await load()
  }

  const vehicleName = (id: number) => vehicles.find(v => v.id === id)?.name ?? `Vehicle #${id}`
  const selectableDefects = defects.filter(d => !order.vehicle_id || d.vehicle_id === Number(order.vehicle_id))

  return <section className="motion-stagger">
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Maintenance operations</p><h1 className="text-3xl font-bold tracking-tight">Inspection to repair</h1><p className="mt-2 text-slate-500">Capture defects, prioritize repairs, and keep their cost and resolution history connected.</p></div><button onClick={() => void load()} className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold">Refresh</button></div>
    {message && <p className="mb-5 rounded-xl bg-mist p-3 text-sm text-forest">{message}</p>}
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-bold">Predictive maintenance watchlist</h2><p className="mt-1 text-sm text-slate-500">Explainable risk from due plans, defects, work orders, and diagnostic telemetry.</p></div><span className="text-xs font-bold uppercase text-slate-400">30-day signals</span></div><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{predictions.slice(0, 4).map(item => <article key={item.vehicle_id} className="rounded-xl bg-mist p-4"><div className="flex items-center justify-between gap-2"><strong className="truncate">{item.vehicle_name}</strong><span className={`text-xs font-bold uppercase ${item.risk_level === 'critical' ? 'text-red-700' : item.risk_level === 'high' ? 'text-orange-700' : 'text-forest'}`}>{item.risk_level} · {item.risk_score}</span></div><p className="mt-2 text-xs text-slate-500">{item.predicted_failure_window_days ? `Review within ${item.predicted_failure_window_days} days` : 'No near-term failure window'}</p><p className="mt-2 text-xs">{item.factors[0]}</p></article>)}{!predictions.length && <p className="text-sm text-slate-400">No vehicle predictions available yet.</p>}</div></div>
    <div className="grid gap-6 xl:grid-cols-2">
      <form onSubmit={submitInspection} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">1. Submit inspection</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Vehicle<select required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={inspection.vehicle_id} onChange={e => setInspection({ ...inspection, vehicle_id: e.target.value })}><option value="">Select vehicle</option>{vehicles.map(v => <option value={v.id} key={v.id}>{v.name}{v.license_plate ? ` · ${v.license_plate}` : ''}</option>)}</select></label><label className="text-sm font-semibold">Inspection type<select className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={inspection.inspection_type} onChange={e => setInspection({ ...inspection, inspection_type: e.target.value })}><option value="pre_trip">Pre-trip</option><option value="post_trip">Post-trip</option><option value="periodic">Periodic</option></select></label></div><label className="mt-4 block text-sm font-semibold">Inspection notes<textarea className="mt-2 min-h-20 w-full rounded-xl border border-slate-200 p-3" value={inspection.notes} onChange={e => setInspection({ ...inspection, notes: e.target.value })} /></label><div className="mt-4 grid gap-4 sm:grid-cols-[1fr_140px]"><label className="text-sm font-semibold">Defect found (optional)<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" placeholder="e.g. Left brake light out" value={inspection.defect_title} onChange={e => setInspection({ ...inspection, defect_title: e.target.value })} /></label><label className="text-sm font-semibold">Severity<select className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={inspection.severity} onChange={e => setInspection({ ...inspection, severity: e.target.value })}><option>minor</option><option>major</option><option>critical</option></select></label></div><button className="mt-5 w-full rounded-xl bg-forest p-3 font-bold text-white">Submit inspection</button></form>
      <form onSubmit={submitWorkOrder} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">2. Create work order</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Vehicle<select required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={order.vehicle_id} onChange={e => setOrder({ ...order, vehicle_id: e.target.value, defect_id: '' })}><option value="">Select vehicle</option>{vehicles.map(v => <option value={v.id} key={v.id}>{v.name}</option>)}</select></label><label className="text-sm font-semibold">Open defect<select className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={order.defect_id} onChange={e => setOrder({ ...order, defect_id: e.target.value })}><option value="">Not linked to a defect</option>{selectableDefects.map(d => <option value={d.id} key={d.id}>{d.title} ({d.severity})</option>)}</select></label></div><div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Work title<input required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={order.title} onChange={e => setOrder({ ...order, title: e.target.value })} /></label><label className="text-sm font-semibold">Vendor<select className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={order.vendor_id} onChange={e => setOrder({ ...order, vendor_id: e.target.value })}><option value="">Internal / unassigned</option>{vendors.map(v => <option value={v.id} key={v.id}>{v.name}</option>)}</select></label></div><div className="mt-4 grid grid-cols-3 gap-3">{(['labor_cost', 'parts_cost', 'external_cost'] as const).map(key => <label key={key} className="text-xs font-semibold capitalize">{key.replace('_', ' ')}<input min="0" step="0.01" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm" value={order[key]} onChange={e => setOrder({ ...order, [key]: e.target.value })} /></label>)}</div><button className="mt-5 w-full rounded-xl bg-forest p-3 font-bold text-white">Create work order</button></form>
    </div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[0.8fr_1.2fr]"><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Open defects</h2><div className="mt-4 space-y-3">{defects.map(d => <article key={d.id} className="rounded-xl bg-mist p-4"><div className="flex justify-between gap-2"><strong>{d.title}</strong><span className="text-xs font-bold uppercase text-forest">{d.severity}</span></div><p className="mt-1 text-sm text-slate-500">{vehicleName(d.vehicle_id)} · {new Date(d.reported_at).toLocaleDateString()}</p></article>)}{!defects.length && <p className="py-8 text-center text-sm text-slate-400">No open defects.</p>}</div></div><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Work orders</h2><div className="mt-4 space-y-3">{orders.map(o => <article key={o.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-mist p-4"><div><strong>{o.title}</strong><p className="mt-1 text-sm text-slate-500">{vehicleName(o.vehicle_id)} · {o.priority} priority · {money(o.total_cost)}{o.downtime_started_at ? ' · downtime' : ''}</p></div>{o.status === 'completed' ? <span className="text-sm font-bold text-forest">Completed</span> : <div className="flex gap-2"><button onClick={() => void toggleDowntime(o)} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold">{o.downtime_started_at && !o.downtime_ended_at ? 'Stop downtime' : 'Start downtime'}</button><button onClick={() => void complete(o.id)} className="rounded-lg bg-forest px-3 py-2 text-xs font-bold text-white">Complete</button></div>}</article>)}{!orders.length && <p className="py-8 text-center text-sm text-slate-400">No work orders yet.</p>}</div></div></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[0.8fr_1.2fr]"><form onSubmit={submitPlan} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">3. Schedule recurring service</h2><div className="mt-5 space-y-4"><label className="block text-sm font-semibold">Vehicle<select required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={plan.vehicle_id} onChange={e => setPlan({ ...plan, vehicle_id: e.target.value })}><option value="">Select vehicle</option>{vehicles.map(v => <option value={v.id} key={v.id}>{v.name}</option>)}</select></label><label className="block text-sm font-semibold">Service name<input required className="mt-2 w-full rounded-xl border border-slate-200 p-3" placeholder="e.g. Engine oil and filter" value={plan.name} onChange={e => setPlan({ ...plan, name: e.target.value })} /></label><div className="grid grid-cols-2 gap-3"><label className="text-xs font-semibold">Every km<input min="0" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm" value={plan.interval_km} onChange={e => setPlan({ ...plan, interval_km: e.target.value })} /></label><label className="text-xs font-semibold">Every engine hours<input min="0" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm" value={plan.interval_hours} onChange={e => setPlan({ ...plan, interval_hours: e.target.value })} /></label></div><button className="w-full rounded-xl bg-forest p-3 font-bold text-white">Create service plan</button></div></form><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Service plans</h2><div className="mt-4 space-y-3">{plans.map(p => <article key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-mist p-4"><div><strong>{p.name}</strong><p className="mt-1 text-sm text-slate-500">{vehicleName(p.vehicle_id)} · {[p.interval_distance_m && `every ${(p.interval_distance_m / 1000).toLocaleString()} km`, p.interval_engine_hours_s && `every ${(p.interval_engine_hours_s / 3600).toLocaleString()} h`].filter(Boolean).join(' · ')}</p></div>{p.due ? <button onClick={() => void createDueOrder(p.id)} className="rounded-lg bg-lime px-3 py-2 text-xs font-bold text-forest">Create due work order</button> : <span className="text-xs font-bold uppercase text-slate-400">On schedule</span>}</article>)}{!plans.length && <p className="py-8 text-center text-sm text-slate-400">No service plans yet.</p>}</div></div></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-2"><form onSubmit={submitPart} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">4. Add inventory part</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Part name<input required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={part.name} onChange={e => setPart({ ...part, name: e.target.value })} /></label><label className="text-sm font-semibold">SKU<input required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={part.sku} onChange={e => setPart({ ...part, sku: e.target.value })} /></label><label className="text-sm font-semibold">On hand<input required min="0" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={part.quantity_on_hand} onChange={e => setPart({ ...part, quantity_on_hand: e.target.value })} /></label><label className="text-sm font-semibold">Reorder level<input min="0" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={part.reorder_level} onChange={e => setPart({ ...part, reorder_level: e.target.value })} /></label></div><label className="mt-4 block text-sm font-semibold">Unit cost (₹)<input min="0" step="0.01" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={part.unit_cost} onChange={e => setPart({ ...part, unit_cost: e.target.value })} /></label><button className="mt-5 w-full rounded-xl bg-forest p-3 font-bold text-white">Add part</button></form><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Reserve part for work order</h2><form className="mt-5 space-y-4" onSubmit={assignPart}><label className="block text-sm font-semibold">Work order<select required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={partUse.work_order_id} onChange={e => setPartUse({ ...partUse, work_order_id: e.target.value })}><option value="">Select open work order</option>{orders.filter(o => !['completed', 'cancelled'].includes(o.status)).map(o => <option value={o.id} key={o.id}>{o.title}</option>)}</select></label><label className="block text-sm font-semibold">Part<select required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={partUse.part_id} onChange={e => setPartUse({ ...partUse, part_id: e.target.value })}><option value="">Select part</option>{parts.map(p => <option value={p.id} key={p.id}>{p.name} · {p.quantity_on_hand} in stock</option>)}</select></label><label className="block text-sm font-semibold">Quantity<input required min="0.01" step="0.01" type="number" className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={partUse.quantity} onChange={e => setPartUse({ ...partUse, quantity: e.target.value })} /></label><button className="w-full rounded-xl bg-forest p-3 font-bold text-white">Reserve part</button></form><div className="mt-5 border-t border-slate-100 pt-4 text-sm text-slate-500">{parts.filter(p => p.low_stock).map(p => <p key={p.id}>Low stock: <strong>{p.name}</strong> ({p.quantity_on_hand} left)</p>)}{!parts.filter(p => p.low_stock).length && 'All inventory is above its reorder level.'}</div></div></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-2"><form onSubmit={submitVendor} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">5. Add service vendor</h2><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Vendor name<input required className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={vendor.name} onChange={e => setVendor({ ...vendor, name: e.target.value })} /></label><label className="text-sm font-semibold">Contact<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={vendor.contact_name} onChange={e => setVendor({ ...vendor, contact_name: e.target.value })} /></label><label className="text-sm font-semibold">Phone<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={vendor.phone} onChange={e => setVendor({ ...vendor, phone: e.target.value })} /></label><label className="text-sm font-semibold">Email<input type="email" className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={vendor.email} onChange={e => setVendor({ ...vendor, email: e.target.value })} /></label></div><button className="mt-5 w-full rounded-xl bg-forest p-3 font-bold text-white">Add vendor</button></form><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Active vendors</h2><div className="mt-4 space-y-3">{vendors.map(v => <article key={v.id} className="rounded-xl bg-mist p-4"><strong>{v.name}</strong><p className="mt-1 text-sm text-slate-500">{[v.contact_name, v.phone].filter(Boolean).join(' · ') || 'No contact details'}</p></article>)}{!vendors.length && <p className="py-8 text-center text-sm text-slate-400">No service vendors yet.</p>}</div></div></div>
  </section>
}
