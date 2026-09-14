export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message) }
}

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? ''

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return response.json() as Promise<T>
}
