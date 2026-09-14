import { ModulePage } from '@/components/layout/ModulePage'
export default function ApiKeysPage() { return <ModulePage resourceType="api-keys" eyebrow="Administration" title="API keys" description="Issue, rotate, and revoke partner integration credentials." primaryAction="Create API key" columns={['Name', 'Created', 'Last used', 'Status', 'Actions']} /> }
