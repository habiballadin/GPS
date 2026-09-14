import { ModulePage } from '@/components/layout/ModulePage'
export default function ShiftsPage() { return <ModulePage resourceType="shifts" eyebrow="Workforce" title="Shifts" description="Plan duty windows, availability, and coverage." primaryAction="Create shift" columns={['Shift', 'Team', 'Start', 'End', 'Status']} /> }
