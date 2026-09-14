export type Role = 'owner' | 'admin' | 'fleet_manager' | 'dispatcher' | 'maintenance' | 'safety' | 'finance' | 'driver' | 'analyst'
export type Permission = `${string}:${string}`

export function can(role: Role, permission: Permission): boolean {
  if (role === 'owner' || role === 'admin') return true
  const [domain] = permission.split(':')
  return role === 'dispatcher' ? ['fleet', 'dispatch', 'trips', 'telemetry'].includes(domain) : role === 'analyst' && permission.endsWith(':read')
}
