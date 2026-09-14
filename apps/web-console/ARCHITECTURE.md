# Fleet web console architecture

This app is the Next.js TypeScript frontend for the fleet operations command center. It is now the Docker Compose frontend; the former Vite app is retained temporarily as a migration reference until the new console is fully validated.

## Boundaries

- `app/`: routing, layouts, loading/error boundaries, and server-component composition.
- `components/`: reusable presentation components with no domain API calls.
- `features/`: domain-owned UI, hooks, API functions, validation, types, state, and tests.
- `lib/api`: typed HTTP client and error normalization.
- `lib/realtime`: WebSocket/SSE lifecycle and reconnect behavior.
- `lib/permissions`: role and permission checks used for visibility only; backend authorization is authoritative.
- `types/`: shared contracts that map to backend OpenAPI/event schemas.
- `stores/`: small client-only global state such as active organization and map viewport.

## Route groups

`(auth)` isolates unauthenticated flows. `(dashboard)` provides the persistent application shell for command center, fleet, operations, maintenance, safety, finance, reports, AI, and settings.

## Implementation order

1. Replace placeholder routes with OpenAPI-generated API types.
2. Add auth/session provider and organization switcher.
3. Implement vehicle/device registration against `/api/v1/vehicles`.
4. Add MapLibre behind `components/maps` and `lib/maps` provider interfaces.
5. Connect live positions to `/api/v1/ws/live` with reconnect and stale-data indicators.
6. Add TanStack Query feature hooks, forms, optimistic updates, and tests.
7. Add role-aware navigation, audit views, and AI approval flows.
