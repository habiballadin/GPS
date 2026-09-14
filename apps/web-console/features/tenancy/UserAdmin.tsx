'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

type Member = { id: number; email: string; role: string }

export function UserAdmin() {
  const { token } = useAuth()
  const [members, setMembers] = useState<Member[]>([])
  const [form, setForm] = useState({ email: '', role: 'operator' })
  const [message, setMessage] = useState('')
  const load = async () => { const response = await fetch('/api/v1/users', { headers: { Authorization: `Bearer ${token}` } }); if (response.ok) setMembers(await response.json()); else setMessage('Only administrators and managers can view users.') }
  useEffect(() => { if (token) void load() }, [token])
  const submit = async (event: FormEvent) => { event.preventDefault(); setMessage(''); const response = await fetch('/api/v1/users/invite', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(form) }); if (!response.ok) { setMessage((await response.json().catch(() => null))?.detail ?? 'Could not create invitation'); return }; setForm({ email: '', role: 'operator' }); setMessage('Invitation created. The user will receive an email when SMTP is configured.'); await load() }
  const changeRole = async (id: number, role: string) => { await fetch(`/api/v1/users/${id}/role`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ role }) }); await load() }
  return <section><div className="mb-8"><p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">Administration</p><h1 className="text-3xl font-bold tracking-tight">Users and roles</h1><p className="mt-2 text-slate-500">Invite workspace members and control their access level.</p></div><div className="grid gap-6 xl:grid-cols-[0.7fr_1.3fr]"><form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Invite user</h2><div className="mt-5 space-y-4"><label className="block text-sm font-semibold">Email<input className="mt-2 w-full rounded-xl border border-slate-200 p-3" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label><label className="block text-sm font-semibold">Role<select className="mt-2 w-full rounded-xl border border-slate-200 p-3" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="manager">Manager</option></select></label>{message && <p className="rounded-xl bg-mist p-3 text-sm text-forest">{message}</p>}<button className="w-full rounded-xl bg-forest p-3 font-bold text-white">Send invitation</button></div></form><div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"><h2 className="text-lg font-bold">Workspace members</h2><div className="mt-5 space-y-3">{members.map(member => <div className="flex items-center justify-between rounded-xl bg-mist p-4" key={member.id}><strong>{member.email}</strong><select className="rounded-lg border border-slate-200 bg-white p-2 text-sm" value={member.role} onChange={e => void changeRole(member.id, e.target.value)}><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="manager">Manager</option><option value="admin">Admin</option></select></div>)}{members.length === 0 && <p className="py-10 text-center text-sm text-slate-400">No members found.</p>}</div></div></div></section>
}
