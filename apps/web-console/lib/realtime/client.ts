export type RealtimeStatus = 'connecting' | 'open' | 'closed' | 'error'

export function createRealtimeClient(path: string, token: string, onMessage: (payload: unknown) => void) {
  const configuredUrl = process.env.NEXT_PUBLIC_WS_URL
  const browserUrl = typeof window === 'undefined' ? '' : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  const url = `${configuredUrl ?? browserUrl}${path}?token=${encodeURIComponent(token)}`
  const socket = new WebSocket(url)
  socket.addEventListener('message', (event) => onMessage(JSON.parse(event.data) as unknown))
  return { close: () => socket.close(), socket }
}
