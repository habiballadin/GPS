import { ModulePage } from '@/components/layout/ModulePage'
export default function InvestigationsPage() { return <ModulePage resourceType="investigations" eyebrow="Safety" title="Investigations" description="Coordinate evidence, owners, findings, and approvals." primaryAction="Start investigation" columns={['Investigation', 'Owner', 'Due', 'Status', 'Actions']} /> }
