import { ModulePage } from '@/components/layout/ModulePage'
export default function WorkOrdersPage() { return <ModulePage resourceType="work-orders" eyebrow="Maintenance" title="Work orders" description="Create, assign, and close vehicle maintenance work." primaryAction="Create work order" columns={['Work order', 'Vehicle', 'Priority', 'Due', 'Status']} /> }
