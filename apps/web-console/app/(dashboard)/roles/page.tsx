import { ModulePage } from '@/components/layout/ModulePage'
export default function RolesPage() { return <ModulePage resourceType="roles" eyebrow="Administration" title="Roles and permissions" description="Configure role access across fleet operating domains." primaryAction="Create role" columns={['Role', 'Users', 'Permissions', 'Updated', 'Actions']} /> }
