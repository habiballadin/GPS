import { ModulePage } from '@/components/layout/ModulePage'
export default function CorrectiveActionsPage() { return <ModulePage resourceType="corrective-actions" eyebrow="Safety" title="Corrective actions" description="Track safety follow-ups and accountability to completion." primaryAction="Add action" columns={['Action', 'Incident', 'Owner', 'Due', 'Status']} /> }
