import { ResourceWorkspace } from '@/components/layout/ResourceWorkspace'

export function DomainPage({ title, description, resourceType = title.toLowerCase().replaceAll(' ', '-') }: Readonly<{ title: string; description: string; resourceType?: string }>) {
  return <ResourceWorkspace resourceType={resourceType} eyebrow="Operations" title={title} description={description} primaryAction={`Create ${title.toLowerCase().replace(/s$/, '')}`} />
}
