import { ModulePage } from '@/components/layout/ModulePage'
export default function IncidentsPage() { return <ModulePage resourceType="incidents" eyebrow="Safety" title="Incidents" description="Manage incident reports, evidence, investigation, and resolution." primaryAction="Report incident" columns={['Incident', 'Location', 'Severity', 'Created', 'Status']} /> }
