import { ModulePage } from '@/components/layout/ModulePage'
export default function UsersPage() { return <ModulePage resourceType="users" eyebrow="Administration" title="Users" description="Invite operators, manage roles, and review access status." primaryAction="Invite user" columns={['User', 'Role', 'Last active', 'Status', 'Actions']} /> }
