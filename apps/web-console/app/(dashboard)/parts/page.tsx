import { ModulePage } from '@/components/layout/ModulePage'
export default function PartsPage() { return <ModulePage resourceType="parts" eyebrow="Maintenance" title="Parts" description="Manage inventory, reorder levels, and usage by work order." primaryAction="Add part" columns={['Part', 'SKU', 'Stock', 'Reorder level', 'Actions']} /> }
